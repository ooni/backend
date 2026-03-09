import asyncio
import io
import logging
import random
from datetime import datetime, timezone
from hashlib import sha512
from typing import List, Dict, Any

import httpx
from fastapi import Request, Response, APIRouter, Header
from pydantic import Field
import zstd

from ..common.metrics import timer
from ..common.routers import BaseModel
from ..common.utils import setnocacheresponse
from ..common.dependencies import ClickhouseDep
from ..dependencies import SettingsDep, ASNReaderDep, CCReaderDep, S3ClientDep
from ..utils import (
    generate_report_id,
)

from ..utils import error, compare_probe_msmt_cc_asn
from ..metrics import Metrics

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
    cc_reader: CCReaderDep,
    asn_reader: ASNReaderDep,
    settings: SettingsDep,
    s3_client: S3ClientDep,
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
        error("Incorrect format")

    if asn_i == 0:
        log.info("Discarding ASN == 0")
        Metrics.MSMNT_DISCARD_ASN0.inc()
        return empty_measurement

    if cc.upper() == "ZZ":
        log.info("Discarding CC == ZZ")
        Metrics.MSMNT_DISCARD_CC_ZZ.inc()
        return empty_measurement

    data = await request.body()
    if content_encoding == "zstd":
        try:
            compressed_len = len(data)
            data = zstd.decompress(data)
            log.debug(f"Zstd compression ratio {compressed_len / len(data)}")
        except Exception as e:
            log.info(f"Failed zstd decompression. Error: {e}")
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
    N_RETRIES = 3
    for t in range(N_RETRIES):
        try:
            url = f"{settings.fastpath_url}/{msmt_uid}"

            async with httpx.AsyncClient() as client:
                resp = await client.post(url, content=data, timeout=59)

            assert resp.status_code == 200, resp.content

            compare_probe_msmt_cc_asn(
                msmt_uid, cc, asn, request, cc_reader, asn_reader, clickhouse
            )
            return ReceiveMeasurementResponse(measurement_uid=msmt_uid)

        except Exception as exc:
            log.error(
                f"[Try {t+1}/{N_RETRIES}] Error trying to send measurement to the fastpath. Error: {exc}"
            )
            sleep_time = random.uniform(0, min(3, 0.3 * 2**t))
            await asyncio.sleep(sleep_time)

    Metrics.SEND_FASTPATH_FAILURE.inc()

    # wasn't possible to send msmnt to fastpath, try to send it to s3
    try:
        s3_client.upload_fileobj(
            io.BytesIO(data), Bucket=settings.failed_reports_bucket, Key=report_id
        )
    except Exception as exc:
        log.error(f"Unable to upload measurement to s3. Error: {exc}")
        Metrics.SEND_S3_FAILURE.inc()

    log.error(f"Unable to send report to fastpath. report_id: {report_id}")
    Metrics.MISSED_MSMNTS.inc()
    return empty_measurement


@timer(name="close_report")
@router.post("/report/{report_id}/close", tags=["reports"])
def close_report(report_id):
    """
    Close a report
    """
    return {}
