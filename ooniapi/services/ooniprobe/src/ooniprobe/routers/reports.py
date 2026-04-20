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
    error,
    generate_report_id,
    get_cc_asn,
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
    Submit measurement
    """
    setnocacheresponse(response)
    empty_measurement = {}
    try:
        rid_timestamp, test_name, cc, asn, format_cid, rand = report_id.split("_")
    except Exception as e:
        log.info(
            f"Unexpected report_id {report_id[:200]}. Error: {e}",
        )
        Metrics.BAD_MEASUREMENTS_CNT.labels(reason="bad_report_id").inc()
        raise error("Incorrect format")

    # TODO validate the timestamp?
    good = len(cc) == 2 and test_name.isalnum() and 1 < len(test_name) < 30
    if not good:
        log.info("Unexpected report_id %r", report_id[:200])
        error("Incorrect format")

    try:
        asn_i = int(asn)
    except ValueError as e:
        log.info(f"ASN value not parsable {asn}. Error: {e}")
        Metrics.BAD_MEASUREMENTS_CNT.labels(reason="bad_asn").inc()
        error("Incorrect format")

    if asn_i == 0:
        log.info("Discarding ASN == 0")
        Metrics.BAD_MEASUREMENTS_CNT.labels(reason="asn_0").inc()
        return empty_measurement

    if cc.upper() == "ZZ":
        log.info("Discarding CC == ZZ")
        Metrics.BAD_MEASUREMENTS_CNT.labels(reason="cc_zz").inc()
        return empty_measurement

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

    # Write the whole body of the measurement in a directory based on a 1-hour
    # time window
    now = datetime.now(timezone.utc)
    h = sha512(data).hexdigest()[:16]
    ts = now.strftime("%Y%m%d%H%M%S.%f")

    # msmt_uid is a unique id based on upload time, cc, testname and hash
    msmt_uid = f"{ts}_{cc}_{test_name}_{h}"
    Metrics.MSMNT_RECEIVED_CNT.inc()

    # Use exponential back off with jitter between retries
    client = request.app.state.fastpath_client
    N_RETRIES = 3
    success = False
    for t in range(N_RETRIES):
        try:
            url = f"{settings.fastpath_url}/{msmt_uid}"

            resp = await client.post(url, content=data)

            assert resp.status_code == 200, resp.content

            success = True
            break

        except Exception as exc:
            log.error(
                f"[Try {t + 1}/{N_RETRIES}] Error trying to send measurement to the fastpath ({settings.fastpath_url}). Error: {exc}"
            )
            sleep_time = random.uniform(0.3, 2 ** (t + 1))
            await asyncio.sleep(sleep_time)

    if success:
        try:  # Make sure an error in this function won't trigger a retry
            await run_in_threadpool(
                _check_and_register_geoip_anomaly,
                request,
                asn_cc_reader,
                clickhouse,
                cc,
                asn,
                msmt_uid,
                data,
            )
        except Exception as e:
            log.error(f"Error checking for geoip anomalies: {e}")

        return ReceiveMeasurementResponse(measurement_uid=msmt_uid)

    Metrics.SEND_FASTPATH_FAILURE.inc()

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

def _check_and_register_geoip_anomaly(
    request: Request,
    asn_cc_reader: ASNCCReaderDep,
    clickhouse: ClickhouseDep,
    cc: str,
    asn: str,
    msmt_uid: str,
    data: bytes,
) -> None:
    # check for geoip anomalies
    actual_cc, actual_asn = get_cc_asn(request, asn_cc_reader)
    if actual_cc != cc or normalize_asn(actual_asn) != normalize_asn(asn):
        # expensive: parses measurement body and sends anomaly to clickhouse
        platform, software_name, software_version = _parse_metadata(data)
        register_geoip_anomaly(
            cc,
            actual_cc,
            asn,
            actual_asn,
            clickhouse,
            msmt_uid,
            platform,
            software_name,
            software_version,
        )
    else:
        Metrics.PROBE_CC_ASN_MATCH.inc()


def _parse_metadata(data: bytes) -> Tuple[str, str, str]:
    """
    Parse measurement body, and return the following metadata:

    platform, software_name, software_version
    """
    try:
        body = ujson.loads(data.decode("utf-8"))
    except Exception as e:
        log.error(f"Couldn't parse json body: {e}")
        return ("", "", "")
    content = body.get("content") or {}
    annotations = content.get("annotations") or {}
    platform = annotations.get("platform") or ""
    software_name = content.get("software_name") or ""
    software_version = content.get("software_version") or ""
    return (platform, software_name, software_version)


@timer(name="close_report")
@router.post("/report/{report_id}/close", tags=["reports"])
def close_report(report_id):
    """
    Close a report
    """
    return {}
