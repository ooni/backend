import io
import logging
from datetime import datetime, timezone
from hashlib import sha512
from typing import Any, Dict, List, Tuple

import ujson
import zstd
from fastapi import APIRouter, Header, Request, Response
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from ..common.dependencies import ClickhouseDep
from ..common.metrics import timer
from ..common.routers import BaseModel
from ..common.utils import setnocacheresponse
from ..dependencies import ASNCCReaderDep, SettingsDep
from ..metrics import Metrics
from ..utils import (
    MeasurementMetadata,
    error,
    generate_report_id,
    get_cc_asn,
    metadata_from_measurement_content,
    normalize_asn,
    register_geoip_anomaly,
)

router = APIRouter()

log = logging.getLogger(__name__)


class OpenReportRequest(BaseModel):
    """
    Open report
    """

    data_format_version: str
    format: str
    probe_asn: str = "AS0"
    probe_cc: str = "ZZ"
    software_name: str
    software_version: str
    test_name: str = ""
    test_start_time: str
    test_version: str


class OpenReportResponse(BaseModel):
    """
    Open report confirmation
    """

    backend_version: str
    report_id: str
    supported_formats: List[str]


@timer(name="open_report")
@router.post("/report", tags=["reports"], response_model=OpenReportResponse)
def open_report(
    data: OpenReportRequest, response: Response, settings: SettingsDep
) -> OpenReportResponse:
    """
    Opens a new report
    """

    log.info("Open report %r", data.model_dump())
    asn = data.probe_asn.upper()
    if len(asn) > 12 or len(asn) < 3 or not asn.startswith("AS"):
        asn = "AS0"
    try:
        asn_i = int(asn[2:])
    except Exception:
        asn_i = 0

    cc = data.probe_cc.upper().replace("_", "")
    if len(cc) != 2:
        cc = "ZZ"
    test_name = data.test_name.lower()
    rid = generate_report_id(test_name, settings, cc, asn_i)
    resp = OpenReportResponse(
        backend_version="1.3.5", supported_formats=["yaml", "json"], report_id=rid
    )
    setnocacheresponse(response)
    return resp


class ReceiveMeasurementResponse(BaseModel):
    """
    Acknowledge
    """

    measurement_uid: str | None = Field(
        examples=["20210208220710.181572_MA_ndt_7888edc7748936bf"], default=None
    )


@timer(name="receive_measurement")
@router.post("/report/{report_id}", tags=["reports"])
async def receive_measurement(
    report_id: str,
    request: Request,
    response: Response,
    asn_cc_reader: ASNCCReaderDep,
    settings: SettingsDep,
    clickhouse: ClickhouseDep,
    content_encoding: str = Header(default=None),
) -> ReceiveMeasurementResponse | Dict[str, Any]:
    """
    Submit measurement.

    The `report_id` path parameter is accepted for URL backwards
    compatibility but is ignored: metadata used to identify
    and validate the measurement is read from the body
    """
    setnocacheresponse(response)
    empty_measurement = {}

    with Metrics.READ_BODY_TIMING.time():
        data = await request.body()

    if content_encoding == "zstd":
        try:
            compressed_len = len(data)
            data = zstd.decompress(data)
            log.debug(f"Zstd compression ratio {compressed_len / len(data)}")
        except Exception as e:
            log.info(f"Failed zstd decompression. Error: {e}")
            Metrics.BAD_MEASUREMENTS_CNT.labels(reason="zstd_fail").inc()
            error("Incorrect format")

    try:
        data, metadata = await run_in_threadpool(_process_measurement_body, data)
    except Exception as e:
        log.info("Failed to parse and modify measurement body")
        log.exception(e)
        Metrics.BAD_MEASUREMENTS_CNT.labels(reason="bad_json").inc()
        error("Incorrect format")

    test_name = metadata.test_name
    cc = metadata.probe_cc
    asn = metadata.probe_asn
    asn_i = normalize_asn(asn)

    # Same validation as old report_id
    cc_ok = len(cc) == 2
    test_name_alnum_ok = test_name.isalnum()
    test_name_len_ok = 1 < len(test_name) < 30
    if not (cc_ok and test_name_alnum_ok and test_name_len_ok):
        log.error(
            f"Bad metadata in measurement body: test_name={test_name[:30]}, cc={cc}"
        )
        if not cc_ok:
            Metrics.BAD_MEASUREMENTS_CNT.labels(reason="bad_cc").inc()
        if not test_name_alnum_ok:
            Metrics.BAD_MEASUREMENTS_CNT.labels(
                reason="tn_not_alnum"
            ).inc()
        if not test_name_len_ok:
            Metrics.BAD_MEASUREMENTS_CNT.labels(
                reason="tn_len"
            ).inc()
        error("Incorrect format")

    if asn_i == 0:
        log.info("Discarding ASN == 0")
        Metrics.BAD_MEASUREMENTS_CNT.labels(reason="asn_0").inc()
        return empty_measurement

    if cc == "ZZ":
        log.info("Discarding CC == ZZ")
        Metrics.BAD_MEASUREMENTS_CNT.labels(reason="cc_zz").inc()
        return empty_measurement

    # Write the whole body of the measurement in a directory based on a 1-hour
    # time window
    now = datetime.now(timezone.utc)
    # Hash MUST be computed after adding extra fields
    h = sha512(data).hexdigest()[:16]
    ts = now.strftime("%Y%m%d%H%M%S.%f")

    # msmt_uid is a unique id based on upload time, cc, testname and hash
    msmt_uid = f"{ts}_{cc}_{test_name}_{h}"
    Metrics.MSMNT_RECEIVED_CNT.inc()

    client = request.app.state.fastpath_client
    success = False
    with Metrics.SEND_FASTPATH_TIMING.time():
        try:
            url = f"{settings.fastpath_url}/{msmt_uid}"

            resp = await run_in_threadpool(client.post, url, data=data)
            with resp:
                resp.raise_for_status()
            Metrics.SEND_FASTPATH_CNT.labels(status="ok").inc()
            success = True

        except Exception as e:
            log.exception(f"Unable to send measurement to fastpath ({settings.fastpath_url}): {e}")
            Metrics.SEND_FASTPATH_CNT.labels(status="fail").inc()

    if success:
        # Geoip anomaly detection runs only when the measurement was successfully
        # submitted to the fastpath, so retries don't cause duplicate anomaly entries.
        with Metrics.COMPARE_CC_TIMING.time():
            try:
                await run_in_threadpool(
                    _check_and_register_geoip_anomaly,
                    request,
                    asn_cc_reader,
                    clickhouse,
                    cc,
                    asn,
                    msmt_uid,
                    metadata,
                )
            except Exception as e:
                log.error(f"Error checking for geoip anomalies: {e}")
                Metrics.COMPARE_CC_FAILURE.inc()

        return ReceiveMeasurementResponse(measurement_uid=msmt_uid)

    # wasn't possible to send msmnt to fastpath, try to send it to s3
    ts_prefix = now.strftime("%Y%m%d%H")
    tn = test_name.replace("_", "")
    s3_key = f"postcans/{ts_prefix}/{ts_prefix}_{cc}_{tn}/{msmt_uid}.post"
    with Metrics.SEND_S3_TIMING.time():
        try:
            await run_in_threadpool(
                request.app.state.s3_client.upload_fileobj,
                io.BytesIO(data),
                Bucket=settings.failed_reports_bucket,
                Key=s3_key,
            )
            Metrics.SEND_S3_CNT.labels(status="ok").inc()
            log.error(f"Unable to send report to fastpath. measurement_uid: {msmt_uid}")
            return empty_measurement
        except Exception:
            log.exception("Unable to upload measurement to s3")
            Metrics.SEND_S3_CNT.labels(status="fail").inc()
            return empty_measurement

def _process_measurement_body(data: bytes) -> Tuple[bytes, MeasurementMetadata]:
    """
    - Parse the measurement body
    - extract some metadata fields
    - set `is_verified="u"`
    - re-serialize.
    """

    with Metrics.DESERIALIZE_BODY_TIMING.time():
        json = ujson.loads(data)

    assert isinstance(json, dict)

    content = json.get("content")
    assert isinstance(content, dict)

    metadata = metadata_from_measurement_content(content)

    json["is_verified"] = "u"

    with Metrics.SERIALIZE_BODY_TIMING.time():
        return ujson.dumps(json).encode("utf-8"), metadata


def _check_and_register_geoip_anomaly(
    request: Request,
    asn_cc_reader: ASNCCReaderDep,
    clickhouse: ClickhouseDep,
    cc: str,
    asn: str,
    msmt_uid: str,
    metadata: MeasurementMetadata,
) -> None:
    actual_cc, actual_asn = get_cc_asn(request, asn_cc_reader)
    if actual_cc != cc or normalize_asn(actual_asn) != normalize_asn(asn):
        register_geoip_anomaly(
            cc,
            actual_cc,
            asn,
            actual_asn,
            clickhouse,
            msmt_uid,
            metadata.platform,
            metadata.software_name,
            metadata.software_version,
        )
    else:
        Metrics.PROBE_CC_ASN_MATCH.inc()


@timer(name="close_report")
@router.post("/report/{report_id}/close", tags=["reports"])
def close_report(report_id):
    """
    Close a report
    """
    return {}
