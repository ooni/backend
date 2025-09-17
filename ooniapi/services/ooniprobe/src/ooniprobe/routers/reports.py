from typing import List, Annotated, Dict, Any
import asyncio
from pathlib import Path
import logging
from hashlib import sha512
from urllib.request import urlopen
from datetime import datetime, timezone
import io
import random

from fastapi import Request, Response, APIRouter, HTTPException, Header, Body
import httpx
from pydantic import Field
from prometheus_client import Counter
import zstd

from ..utils import (
    generate_report_id,
    extract_probe_ipaddr,
    lookup_probe_cc,
    lookup_probe_network,
)
from ..dependencies import SettingsDep, ASNReaderDep, CCReaderDep, S3ClientDep
from ..common.routers import BaseModel
from ..common.utils import setnocacheresponse
from ..common.metrics import timer

router = APIRouter()

log = logging.getLogger(__name__)


class Metrics:
    MSMNT_DISCARD_ASN0 = Counter(
        "receive_measurement_discard_asn_0",
        "How many measurements were discarded due to probe_asn == ASN0",
    )

    MSMNT_DISCARD_CC_ZZ = Counter(
        "receive_measurement_discard_cc_zz",
        "How many measurements were discarded due to probe_cc == ZZ",
    )

    MSMNT_RECEIVED_CNT = Counter(
        "receive_measurement_count",
        "Count of incomming measurements",
    )

    PROBE_CC_ASN_MATCH = Counter(
        "probe_cc_asn_match",
        "How many matches between reported and observed probe_cc and asn",
    )

    PROBE_CC_ASN_NO_MATCH = Counter(
        "probe_cc_asn_nomatch",
        "How many mismatches between reported and observed probe_cc and asn",
        labelnames=["mismatch"],
    )

    MISSED_MSMNTS = Counter(
        "missed_msmnts", "Measurements that failed to be sent to the fast path."
    )

    SEND_FASTPATH_FAILURE = Counter(
        "measurement_fastpath_send_failure_count",
        "How many times ooniprobe failed to send a measurement to fastpath",
    )

    SEND_S3_FAILURE = Counter(
        "measurement_s3_upload_failure_count",
        "How many times ooniprobe failed to send a measurement to s3. "
        "Measurements are sent to s3 when they can't be sent to the fastpath",
    )


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
    content_encoding: str = Header(default=None),
) -> ReceiveMeasurementResponse | Dict[str, Any]:
    """
    Submit measurement
    """
    setnocacheresponse(response)
    empty_measurement = {}
    try:
        rid_timestamp, test_name, cc, asn, format_cid, rand = report_id.split("_")
    except Exception:
        log.info("Unexpected report_id %r", report_id[:200])
        raise error("Incorrect format")

    # TODO validate the timestamp?
    good = len(cc) == 2 and test_name.isalnum() and 1 < len(test_name) < 30
    if not good:
        log.info("Unexpected report_id %r", report_id[:200])
        error("Incorrect format")

    try:
        asn_i = int(asn)
    except ValueError:
        log.info("ASN value not parsable %r", asn)
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
            data = zstd.decompress(data)
            ratio = len(data) / len(data)
            log.debug(f"Zstd compression ratio {ratio}")
        except Exception as e:
            log.info("Failed zstd decompression")
            error("Incorrect format")

    # Write the whole body of the measurement in a directory based on a 1-hour
    # time window
    now = datetime.now(timezone.utc)
    h = sha512(data).hexdigest()[:16]
    ts = now.strftime("%Y%m%d%H%M%S.%f")

    # msmt_uid is a unique id based on upload time, cc, testname and hash
    msmt_uid = f"{ts}_{cc}_{test_name}_{h}"
    Metrics.MSMNT_RECEIVED_CNT.inc()

    compare_probe_msmt_cc_asn(cc, asn, request, cc_reader, asn_reader)
    # Use exponential back off with jitter between retries
    N_RETRIES = 3
    for t in range(N_RETRIES):
        try:
            url = f"{settings.fastpath_url}/{msmt_uid}"

            async with httpx.AsyncClient() as client:
                resp = await client.post(url, content=data, timeout=59)
            
            assert resp.status_code == 200, resp.content
            return ReceiveMeasurementResponse(measurement_uid=msmt_uid)

        except Exception as exc:
            log.error(
                f"[Try {t+1}/{N_RETRIES}] Error trying to send measurement to the fastpath. Error: {exc}"
            )
            sleep_time = random.uniform(0, min(3, 0.3 * 2 ** t))
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


def error(msg: str, status_code: int = 400):
    raise HTTPException(status_code=status_code, detail=msg)


def compare_probe_msmt_cc_asn(
    cc: str,
    asn: str,
    request: Request,
    cc_reader: CCReaderDep,
    asn_reader: ASNReaderDep,
):
    """Compares CC/ASN from measurement with CC/ASN from HTTPS connection ipaddr
    Generates a metric.
    """
    try:
        cc = cc.upper()
        ipaddr = extract_probe_ipaddr(request)
        db_probe_cc = lookup_probe_cc(ipaddr, cc_reader)
        db_asn, _ = lookup_probe_network(ipaddr, asn_reader)
        log.info(f"db_cc = {db_probe_cc} - cc = {cc}") 
        log.info(f"db_asn = {db_asn} - asn = {asn}")
        if db_asn.startswith("AS"):
            db_asn = db_asn[2:]
        if db_probe_cc == cc and db_asn == asn:
            Metrics.PROBE_CC_ASN_MATCH.inc()
        elif db_probe_cc != cc:
            Metrics.PROBE_CC_ASN_NO_MATCH.labels(mismatch="cc").inc()
        elif db_asn != asn:
            Metrics.PROBE_CC_ASN_NO_MATCH.labels(mismatch="asn").inc()
    except Exception:
        pass
