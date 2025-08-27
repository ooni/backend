"""
Measurements API
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Any, Dict, Union, TypedDict, Tuple
import gzip
import json
import logging
import math
import time

import ujson
import urllib3

from fastapi import APIRouter, Depends, Query, HTTPException, Header, Response, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from typing_extensions import Annotated

from pydantic import Field

import sqlalchemy as sa
from sqlalchemy import tuple_, Row, sql
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import and_, text, select, column
from sqlalchemy.sql.expression import text as sql_text
from sqlalchemy.sql.expression import table as sql_table
from sqlalchemy.exc import OperationalError
from psycopg2.extensions import QueryCanceledError

from clickhouse_driver import Client as ClickhouseClient

from urllib.request import urlopen
from urllib.parse import urljoin, urlencode

from ...common.config import Settings
from ...common.dependencies import get_settings
from ...common.routers import BaseModel
from ...common.utils import setcacheresponse, commasplit, setnocacheresponse
from ...common.clickhouse_utils import query_click, query_click_one_row
from ...dependencies import get_clickhouse_session

log = logging.getLogger(__name__)

router = APIRouter()

urllib_pool = urllib3.PoolManager()

MeasurementNotFound = HTTPException(status_code=500, detail="Measurement not found")
ReportInputNotFound = HTTPException(
    status_code=500, detail="Report and input not found"
)
MeasurementFileNotFound = HTTPException(
    status_code=404, detail="Measurement S3 file not found"
)
AbortMeasurementList = HTTPException(
    status_code=403, detail="Disallowed list_measurements"
)
Abort504 = HTTPException(status_code=504, detail="Error in list_measurements")


@router.get(
    "/v1/files",
    tags=["files"],
)
def list_files():
    """List files - unsupported"""
    response = JSONResponse(content=jsonable_encoder({"msg": "not implemented"}))
    setcacheresponse("1d", response)
    return response


def _fetch_jsonl_measurement_body_from_s3(
    s3path: str,
    linenum: int,
    s3_bucket_name: str,
) -> bytes:
    """
    Fetch jsonl from S3, decompress it, extract single msmt
    """
    baseurl = get_bucket_url(s3_bucket_name)
    url = urljoin(baseurl, s3path)

    log.info(f"Fetching {url}")
    r = urlopen(url)

    f = gzip.GzipFile(fileobj=r, mode="r")
    for n, line in enumerate(f):
        if n == linenum:
            return line
    raise MeasurementFileNotFound


@router.get(
    "/v1/measurement/{measurement_uid}",
    tags=["oonimeasurements"],
)
def get_measurement(
    measurement_uid: str,
    download: bool,
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings),
):
    """
    Get one measurement by measurement_id,
    Returns only the measurement without extra data from the database
    """
    assert measurement_uid
    s3path, linenum = measurement_uid_to_s3path_linenum(db, measurement_uid)

    log.debug(f"Fetching file {s3path} from S3")
    body = _fetch_jsonl_measurement_body_from_s3(
        s3path, linenum, settings.s3_bucket_name
    )

    response = Response(content=body)
    if download:
        response.headers["Content-Disposition"] = (
            f"attachment; filename=ooni_measurement-{measurement_uid}.json"
        )

    setcacheresponse("1h", response)
    response.media_type = "application/json"
    return response


def _unwrap_post(post: dict) -> dict:
    fmt = post.get("format", "")
    if fmt == "json":
        return post.get("content", {})
    raise Exception("Unexpected format")


def _fetch_measurement_body_from_hosts(
    other_collectors: List[str], measurement_uid: str
) -> Optional[bytes]:
    """
    Fetch raw POST from another API host, extract msmt
    Note: This is used only for msmts that have been processed by the fastpath
    but are not uploaded to S3 yet.
    """
    try:
        assert measurement_uid.startswith("20")
        tstamp, cc, testname, _ = measurement_uid.split("_")
        hour = tstamp[:10]
        int(hour)
        path = f"{hour}_{cc}_{testname}/{measurement_uid}.post"
    except Exception:
        log.info(f"Failed to process measurement {measurement_uid}", exc_info=True)
        return None

    for hostname in other_collectors:
        url = urljoin(f"{hostname}/measurement_spool/", path)
        log.debug(f"Attempt to load {url}")
        try:
            r = urllib_pool.request("GET", url)
            if r.status == 404:
                log.error(f"Measurement {measurement_uid} not found on host {hostname}")
                continue
            elif r.status != 200:
                log.error(
                    f"Unexpected status {r.status} for {measurement_uid} on host {hostname}"
                )
                continue

            post = ujson.loads(r.data)
            body = _unwrap_post(post)
            return ujson.dumps(body).encode()
        except Exception:
            log.info(
                f"Failed to load fetch {measurement_uid} from {hostname}", exc_info=True
            )
            pass

    return None


def measurement_uid_to_s3path_linenum(db: ClickhouseClient, measurement_uid: str):
    """
    Fetch measurement S3 location using measurement_uid
    """
    # TODO: cleanup this
    query = """SELECT s3path, linenum FROM jsonl
        PREWHERE (report_id, input) IN (
            SELECT report_id, input FROM fastpath WHERE measurement_uid = :uid
        )
        LIMIT 1"""
    query_params = dict(uid=measurement_uid)
    lookup = query_click_one_row(db, sql.text(query), query_params, query_prio=3)
    if lookup is None:
        raise MeasurementNotFound

    s3path = lookup["s3path"]
    linenum = lookup["linenum"]
    return s3path, linenum


def _fetch_jsonl_measurement_body_clickhouse(
    db: ClickhouseClient,
    measurement_uid: Optional[str],
    s3_bucket_name: str,
) -> Optional[bytes]:
    """
    Find measurement location in S3 and fetch the measurement
    """
    # TODO: switch to _fetch_measurement_body_by_uid
    if (measurement_uid is None) or (len(measurement_uid) == 0):
        log.error("Invalid measurement_uid provided")
        return None

    try:
        log.debug(f"Fetching s3path and linenum for measurement {measurement_uid}")
        s3path, linenum = measurement_uid_to_s3path_linenum(db, measurement_uid)

        log.debug(f"Fetching file {s3path} from S3")
        return _fetch_jsonl_measurement_body_from_s3(s3path, linenum, s3_bucket_name)
    except Exception as e:
        log.error(f"Failed to fetch {measurement_uid}: {e}", exc_info=True)
        return None


def _fetch_measurement_body(
    db: ClickhouseClient,
    settings: Settings,
    report_id: str,
    measurement_uid: Optional[str],
) -> str:
    """
    Fetch measurement body from either:
        - JSONL files on S3
        - remote measurement spool dir (another API/collector host)
    """
    log.debug(
        f"Fetching body for report_id: {report_id}, measurement_uid: {measurement_uid}"
    )

    u_count = report_id.count("_")
    # Current format e.g. 20210124T210009Z_webconnectivity_VE_22313_n1_Ojb<redacted>
    new_format = u_count == 5 and measurement_uid

    if not new_format:
        body = _fetch_jsonl_measurement_body_clickhouse(
            db, measurement_uid, settings.s3_bucket_name
        )
    else:
        assert measurement_uid
        ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y%m%d%H%M")
        fresh = measurement_uid > ts

        # Do the fetching in different orders based on the likelyhood of success
        if new_format and fresh:
            body = _fetch_measurement_body_from_hosts(
                settings.other_collectors, measurement_uid
            ) or _fetch_jsonl_measurement_body_clickhouse(
                db, measurement_uid, settings.s3_bucket_name
            )
        elif new_format and not fresh:
            body = _fetch_jsonl_measurement_body_clickhouse(
                db, measurement_uid, settings.s3_bucket_name
            ) or _fetch_measurement_body_from_hosts(
                settings.other_collectors, measurement_uid
            )
    if body:
        return body.decode("utf-8")

    raise MeasurementNotFound


class MeasurementMeta(BaseModel):
    input: Optional[str] = None
    measurement_start_time: Optional[datetime] = None
    measurement_uid: Optional[str] = None
    report_id: Optional[str] = None
    test_name: Optional[str] = None
    test_start_time: Optional[datetime] = None
    probe_asn: Optional[str] = None
    probe_cc: Optional[str] = None
    scores: Optional[str] = None
    category_code: Optional[str] = None
    anomaly: Optional[bool] = None
    confirmed: Optional[bool] = None
    failure: Optional[bool] = None
    raw_measurement: Optional[str] = None
    category_code: Optional[str] = None


def format_msmt_meta(msmt_meta: dict) -> MeasurementMeta:
    formatted_msmt_meta = MeasurementMeta(
        input=msmt_meta["input"],
        measurement_start_time=msmt_meta["measurement_start_time"],
        measurement_uid=msmt_meta["measurement_uid"],
        report_id=msmt_meta["report_id"],
        test_name=msmt_meta["test_name"],
        test_start_time=msmt_meta["test_start_time"],
        probe_asn=str(msmt_meta["probe_asn"]),
        probe_cc=msmt_meta["probe_cc"],
        scores=msmt_meta["scores"],
        anomaly=(msmt_meta["anomaly"] == "t"),
        confirmed=(msmt_meta["confirmed"] == "t"),
        failure=(msmt_meta["msm_failure"] == "t"),
        category_code=msmt_meta.get("category_code", None),
    )
    return formatted_msmt_meta


def _get_measurement_meta_clickhouse(
    db: ClickhouseClient, report_id: str, input_: Optional[str]
) -> MeasurementMeta:
    # Given report_id + input, fetch measurement data from fastpath table
    query = "SELECT * FROM fastpath "
    if input_ is None:
        # fastpath uses input = '' for empty values
        query += "WHERE report_id = :report_id AND input = '' "
    else:
        # Join citizenlab to return category_code (useful only for web conn)
        query += """
        LEFT OUTER JOIN citizenlab ON citizenlab.url = fastpath.input
        WHERE fastpath.input = :input
        AND fastpath.report_id = :report_id
        """
    query_params = dict(input=input_, report_id=report_id)
    query += "LIMIT 1"
    msmt_meta = query_click_one_row(db, sql.text(query), query_params, query_prio=3)
    if not msmt_meta:
        return MeasurementMeta()  # measurement not found
    if msmt_meta["probe_asn"] == 0:
        # https://ooni.org/post/2020-ooni-probe-asn-incident-report/
        # https://github.com/ooni/explorer/issues/495
        return MeasurementMeta()  # unwanted

    return format_msmt_meta(msmt_meta)


def _get_measurement_meta_by_uid(
    db: ClickhouseClient, measurement_uid: str
) -> MeasurementMeta:
    """
    Get measurement meta from measurement_uid
    """
    query = """SELECT * FROM fastpath
        LEFT OUTER JOIN citizenlab ON citizenlab.url = fastpath.input
        WHERE measurement_uid = :uid
        LIMIT 1
    """
    query_params = dict(uid=measurement_uid)
    msmt_meta = query_click_one_row(db, sql.text(query), query_params, query_prio=3)
    if not msmt_meta:
        return MeasurementMeta()  # measurement not found
    if msmt_meta["probe_asn"] == 0:
        # https://ooni.org/post/2020-ooni-probe-asn-incident-report/
        # https://github.com/ooni/explorer/issues/495
        return MeasurementMeta()  # unwanted

    return format_msmt_meta(msmt_meta)


@router.get("/v1/raw_measurement")
async def get_raw_measurement(
    response: Response,
    report_id: Annotated[
        Optional[str],
        Query(description="The report_id to search measurements for", min_length=3),
    ] = None,
    input: Annotated[
        Optional[str],
        Query(
            description="The input (for example a URL or IP address) to search measurements for",
            min_length=3,
        ),
    ] = None,
    measurement_uid: Annotated[
        Optional[str],
        Query(
            description="The measurement_uid to search measurements for", min_length=3
        ),
    ] = None,
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings),
) -> Response:
    """
    Get raw measurement body.

    You should always provide at the least one of: `report_id`, `measurement_uid`
    """
    # This is used by Explorer to let users download msmts
    if measurement_uid:
        log.info(f"get_raw_measurement {measurement_uid}")
        msmt_meta = _get_measurement_meta_by_uid(db, measurement_uid)
    elif report_id:
        log.info(f"get_raw_measurement {report_id} {input}")
        msmt_meta = _get_measurement_meta_clickhouse(db, report_id, input)
    else:
        raise HTTPException(
            status_code=400,
            detail="Either report_id or measurement_uid must be provided",
        )

    if msmt_meta.report_id:
        body = _fetch_measurement_body(
            db, settings, msmt_meta.report_id, msmt_meta.measurement_uid
        )
    else:
        body = "{}"

    response = Response(content=body, media_type="application/json")
    setcacheresponse("1d", response)
    return response


class MeasurementBase(BaseModel):
    anomaly: Optional[bool] = Field(
        default=None, title="check if the measurement is an anomaly"
    )
    confirmed: Optional[bool] = Field(
        default=None, title="check if the measurement is a confirmed block"
    )
    failure: Optional[bool] = Field(
        default=None, title="failure check if measurement is marked as failed"
    )
    input_: Optional[str] = Field(default=None, alias="input")
    probe_asn: Optional[str] = Field(default=None, title="ASN of the measurement probe")
    probe_cc: Optional[str] = Field(default=None, title="country code of the probe ASN")
    report_id: Optional[str] = Field(default=None, title="report id of the measurement")
    scores: Optional[Dict[str, object]] = Field(
        default=None, title="blocking scores of the measurement"
    )
    test_name: Optional[str] = Field(default=None, title="test name of the measurement")


@router.get("/v1/measurement_meta", response_model_exclude_unset=True)
async def get_measurement_meta(
    response: Response,
    measurement_uid: Annotated[
        Optional[str],
        Query(
            description="The measurement ID, mutually exclusive with report_id + input",
            min_length=3,
        ),
    ] = None,
    report_id: Annotated[
        Optional[str],
        Query(
            description=(
                "The report_id to search measurements for example: "
                "20210208T162755Z_ndt_DZ_36947_n1_8swgXi7xNuRUyO9a"
            ),
            min_length=3,
        ),
    ] = None,
    input: Annotated[
        Optional[str],
        Query(
            description="The input (for example a URL or IP address) to search measurements for",
            min_length=3,
        ),
    ] = None,
    full: Annotated[bool, Query(description="Include JSON measurement data")] = False,
    settings=Depends(get_settings),
    db=Depends(get_clickhouse_session),
) -> MeasurementMeta:
    """
    Get metadata on one measurement by measurement_uid or report_id + input
    """

    if measurement_uid:
        log.info(f"get_measurement_meta {measurement_uid}")
        msmt_meta = _get_measurement_meta_by_uid(db, measurement_uid)
    elif report_id:
        log.info(f"get_measurement_meta {report_id} {input}")
        msmt_meta = _get_measurement_meta_clickhouse(db, report_id, input)
    else:
        raise HTTPException(
            status_code=400,
            detail="Either report_id or measurement_uid must be provided",
        )

    setcacheresponse("1m", response)
    body = ""

    if not full:  # return without raw_measurement
        return msmt_meta

    if msmt_meta == {}:  # measurement not found
        return MeasurementMeta(raw_measurement=body)

    try:
        assert isinstance(msmt_meta.report_id, str) and isinstance(
            msmt_meta.measurement_uid, str
        )
        body = _fetch_measurement_body(
            db, settings, msmt_meta.report_id, msmt_meta.measurement_uid
        )
        assert isinstance(body, bytes)
        body = body.decode()
    except Exception as e:
        log.error(e, exc_info=True)

    msmt_meta.raw_measurement = body
    return msmt_meta


class Measurement(MeasurementBase):
    measurement_url: str = Field(title="url of the measurement")
    measurement_start_time: Optional[datetime] = Field(
        default=None, title="start time of the measurement"
    )
    measurement_uid: Optional[str] = Field(default=None, title="uid of the measurement")


class ResultsMetadata(BaseModel):
    count: int = Field(title="")
    current_page: int = Field(title="")
    limit: int = Field(title="")
    next_url: Optional[str] = Field(title="")
    offset: int = Field(title="")
    pages: int = Field(title="")
    query_time: float = Field(title="")


class MeasurementList(BaseModel):
    metadata: ResultsMetadata = Field(title="metadata for query results")
    results: List[Measurement] = Field(title="measurement results")


def genurl(base_url: str, path: str, **kw) -> str:
    """Generate absolute URL for the API"""
    return urljoin(base_url, path) + "?" + urlencode(kw)


@router.get("/v1/measurements")
async def list_measurements(
    request: Request,
    response: Response,
    report_id: Optional[str] = Query(
        None,
        description="Report_id to search measurements for",
        min_length=3,
    ),
    input: Optional[str] = Query(
        None,
        description="Input (for example a URL or IP address) to search measurements for",
        min_length=3,
    ),
    domain: Optional[str] = Query(
        None,
        description="Domain to search measurements for",
        min_length=3,
    ),
    probe_cc: Annotated[
        Optional[str], Query(description="Two letter country code")
    ] = None,
    probe_asn: Annotated[
        Union[str, int, None],
        Query(description='Autonomous system number in the format "ASXXX"'),
    ] = None,
    test_name: Annotated[
        Optional[str],
        Query(description="Name of the test"),
    ] = None,
    category_code: Annotated[
        Optional[str],
        Query(description="Category code from the citizenlab list"),
    ] = None,
    since: Annotated[
        Optional[str],
        Query(
            description='Start date of when measurements were run (ex. "2016-10-20T10:30:00")'
        ),
    ] = None,
    until: Annotated[
        Optional[str],
        Query(
            description='End date of when measurement were run (ex. "2016-10-20T10:30:00")'
        ),
    ] = None,
    confirmed: Annotated[
        Optional[bool],
        Query(
            description=(
                'Set "true" for confirmed network anomalies (we found a blockpage, a middlebox, etc.). '
                "Default: no filtering (show both true and false)"
            )
        ),
    ] = None,
    anomaly: Annotated[
        Optional[bool],
        Query(
            description=(
                'Set "true" for measurements that require special attention (likely to be a case of blocking).'
                "Default: no filtering (show both true and false)"
            )
        ),
    ] = None,
    failure: Annotated[
        Optional[bool],
        Query(
            description=(
                'Set "true" for failed measurements (the control request failed, there was a bug, etc.). '
                "Default: no filtering (show both true and false)"
            )
        ),
    ] = None,
    software_version: Annotated[
        Optional[str],
        Query(description="Filter measurements by software version. Comma-separated."),
    ] = None,
    test_version: Annotated[
        Optional[str],
        Query(description="Filter measurements by test version. Comma-separated."),
    ] = None,
    engine_version: Annotated[
        Optional[str],
        Query(description="Filter measurements by engine version. Comma-separated."),
    ] = None,
    ooni_run_link_id: Annotated[
        Optional[str], Query(description="Filter measurements by OONIRun ID.")
    ] = None,
    order_by: Annotated[
        Optional[str],
        Query(
            description="By which key the results should be ordered by (default: `null`)",
            enum=[
                "test_start_time",
                "measurement_start_time",
                "input",
                "probe_cc",
                "probe_asn",
                "test_name",
            ],
        ),
    ] = None,
    order: Annotated[
        str,
        Query(
            description="If the order should be ascending or descending (one of: `asc` or `desc`)",
            enum=["asc", "desc", "ASC", "DESC"],
        ),
    ] = "asc",
    offset: Annotated[
        int, Query(description="Offset into the result set (default: 0)")
    ] = 0,
    limit: Annotated[
        int, Query(description="Number of records to return (default: 100)")
    ] = 100,
    user_agent: Annotated[str | None, Header()] = None,
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings),
) -> MeasurementList:
    """
    Search for measurements using only the database. Provide pagination.
    """
    # x-code-samples:
    # - lang: 'curl'
    #    source: |
    #    curl "https://api.ooni.io/api/v1/measurements?probe_cc=IT&confirmed=true&since=2017-09-01"
    software_versions = None
    if software_version:
        software_versions = commasplit(software_version)
    test_versions = None
    if test_version:
        test_versions = commasplit(test_version)
    engine_versions = None
    if engine_version:
        engine_versions = commasplit(engine_version)

    # Workaround for https://github.com/ooni/probe/issues/1034
    if user_agent and user_agent.startswith("okhttp"):
        # Cannot be cached due to user_agent
        return MeasurementList(
            metadata=ResultsMetadata(
                count=1,
                current_page=1,
                limit=100,
                next_url=None,
                offset=0,
                pages=1,
                query_time=0.001,
            ),
            results=[Measurement(measurement_url="")],
        )

    ### Prepare query parameters

    until_dt = None
    if until is not None:
        until_dt = datetime.strptime(until, "%Y-%m-%d")

    # Set reasonable since/until ranges if not specified.
    try:
        if until is None:
            if report_id is None:
                t = datetime.now(timezone.utc) + timedelta(days=1)
                until_dt = datetime(t.year, t.month, t.day)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid until parameter")

    since_dt = None
    if since is not None:
        since_dt = datetime.strptime(since, "%Y-%m-%d")

    try:
        if since_dt is None:
            if report_id is None and until_dt is not None:
                since_dt = until_dt - timedelta(days=30)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid since parameter")

    if order.lower() not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="Invalid order parameter")

    ### Perform query

    INULL = ""  # Special value for input = NULL to merge rows with FULL OUTER JOIN

    fpwhere = []

    query_params: Dict[str, Any] = {}

    # Populate WHERE clauses and query_params dict

    if since is not None:
        query_params["since"] = since
        fpwhere.append(sql.text("measurement_start_time > :since"))

    if until is not None:
        query_params["until"] = until
        fpwhere.append(sql.text("measurement_start_time <= :until"))

    if report_id:
        query_params["report_id"] = report_id
        fpwhere.append(sql.text("report_id = :report_id"))

    if probe_cc:
        probe_cc_list = probe_cc.split(",")
        query_params["probe_cc"] = probe_cc_list
        fpwhere.append(sql.text("probe_cc IN :probe_cc"))
    else:
        fpwhere.append(sql.text("probe_cc != 'ZZ'"))

    if probe_asn is not None:
        if isinstance(probe_asn, str):
            probe_asn_list = probe_asn.split(",")
            probe_asn_integer_list = []
            for probe_asn_value in probe_asn_list:
                if probe_asn_value.startswith("AS"):
                    probe_asn_integer_list.append(int(probe_asn_value[2:]))
        query_params["probe_asn"] = probe_asn_integer_list
        fpwhere.append(sql.text("probe_asn IN :probe_asn"))

    else:
        # https://ooni.org/post/2020-ooni-probe-asn-incident-report/
        # https://github.com/ooni/explorer/issues/495
        fpwhere.append(sql.text("probe_asn != 0"))

    if test_name is not None:
        test_name_list = test_name.split(",")
        query_params["test_name"] = test_name_list
        fpwhere.append(sql.text("test_name IN :test_name"))

    if software_versions is not None:
        query_params["software_versions"] = software_versions
        fpwhere.append(sql.text("software_version IN :software_versions"))

    if test_versions is not None:
        query_params["test_versions"] = test_versions
        fpwhere.append(sql.text("test_version IN :test_versions"))

    if engine_versions is not None:
        query_params["engine_versions"] = engine_versions
        fpwhere.append(sql.text("engine_version IN :engine_versions"))

    if ooni_run_link_id is not None:
        query_params["ooni_run_link_id"] = ooni_run_link_id
        fpwhere.append(sql.text("ooni_run_link_id = :ooni_run_link_id"))

    # Filter on anomaly, confirmed and failure:
    # The database stores anomaly and confirmed as boolean + NULL and stores
    # failures in different columns. This leads to many possible combinations
    # but only a subset is used.
    # On anomaly and confirmed: any value != TRUE is treated as FALSE
    # See test_list_measurements_filter_flags_fastpath

    if anomaly is True:
        fpwhere.append(sql.text("fastpath.anomaly = 't'"))

    elif anomaly is False:
        fpwhere.append(sql.text("fastpath.anomaly = 'f'"))

    if confirmed is True:
        fpwhere.append(sql.text("fastpath.confirmed = 't'"))

    elif confirmed is False:
        fpwhere.append(sql.text("fastpath.confirmed = 'f'"))

    if failure is True:
        fpwhere.append(sql.text("fastpath.msm_failure = 't'"))

    elif failure is False:
        fpwhere.append(sql.text("fastpath.msm_failure = 'f'"))

    fpq_table = sql.table("fastpath")

    if input:
        # input_ overrides domain and category_code
        query_params["input"] = input
        fpwhere.append(sql.text("input = :input"))

    elif domain or category_code:
        # both domain and category_code can be set at the same time
        if domain:
            domain_list = domain.split(",")
            query_params["domain"] = domain_list
            fpwhere.append(sql.text("domain IN :domain"))

        if category_code:
            query_params["category_code"] = category_code
            fpq_table = fpq_table.join(
                sql.table("citizenlab"),
                sql.text("citizenlab.url = fastpath.input"),
            )
            fpwhere.append(sql.text("citizenlab.category_code = :category_code"))

    fp_query = select("*").where(and_(*fpwhere)).select_from(fpq_table)

    if order_by is None:
        order_by = "measurement_start_time"

    fp_query = fp_query.order_by(text("{} {}".format(order_by, order)))

    # Assemble the "external" query. Run a final order by followed by limit and
    # offset
    query = fp_query.offset(offset).limit(limit)
    query_params["param_1"] = limit
    query_params["param_2"] = offset

    # Run the query, generate the results list
    iter_start_time = time.time()

    try:
        rows = query_click(db, query, query_params)
        results = []
        for row in rows:
            msmt_uid = row["measurement_uid"]
            url = genurl(
                settings.base_url, "/api/v1/raw_measurement", measurement_uid=msmt_uid
            )
            results.append(
                Measurement(
                    measurement_uid=msmt_uid,
                    measurement_url=url,
                    report_id=row["report_id"],
                    probe_cc=row["probe_cc"],
                    probe_asn="AS{}".format(row["probe_asn"]),
                    test_name=row["test_name"],
                    measurement_start_time=row["measurement_start_time"],
                    input=row["input"],
                    anomaly=row["anomaly"] == "t",  # TODO: This is wrong
                    confirmed=row["confirmed"] == "t",
                    failure=row["msm_failure"] == "t",
                    scores=json.loads(row["scores"]),
                )
            )

    except OperationalError as exc:
        log.error(exc)
        if isinstance(exc.orig, QueryCanceledError):
            # FIXME: this is a postgresql exception!
            # Timeout due to a slow query. Generate metric and do not feed it
            # to Sentry.
            raise Abort504

        raise exc

    # Replace the special value INULL for "input" with None
    for i, r in enumerate(results):
        if r.input_ == INULL:
            results[i].input_ = None

    pages = -1
    count = -1
    current_page = math.ceil(offset / limit) + 1

    # We got less results than what we expected, we know the count and that
    # we are done
    if len(results) < limit:
        count = offset + len(results)
        pages = math.ceil(count / limit)
        next_url = None
    else:
        # XXX this is too intensive. find a workaround
        # count_start_time = time.time()
        # count = q.count()
        # pages = math.ceil(count / limit)
        # current_page = math.ceil(offset / limit) + 1
        # query_time += time.time() - count_start_time
        next_args = dict(request.query_params)
        next_args["offset"] = str(offset + limit)
        next_args["limit"] = str(limit)
        next_url = genurl(settings.base_url, "/api/v1/measurements", **next_args)

    query_time = time.time() - iter_start_time
    metadata = ResultsMetadata(
        offset=offset,
        limit=limit,
        count=count,
        pages=pages,
        current_page=current_page,
        next_url=next_url,
        query_time=query_time,
    )
    setcacheresponse("1m", response)
    return MeasurementList(metadata=metadata, results=results[:limit])


class ErrorResponse(BaseModel):
    v: int
    msg: str


@router.get("/v1/torsf_stats")
async def get_torsf_stats(
    probe_cc: Annotated[Optional[str], Query(description="Two letter country code")],
    since: Annotated[
        Optional[datetime],
        Query(
            description='Start date of when measurements were run (ex. "2016-10-20T10:30:00")'
        ),
    ],
    until: Annotated[
        Optional[datetime],
        Query(
            description='End date of when measurement were run (ex. "2016-10-20T10:30:00")'
        ),
    ],
    response: Response,
    db=Depends(get_clickhouse_session),
):
    """
    Tor Pluggable Transports statistics
    Average / percentiles / total_count grouped by day
    Either group-by or filter by probe_cc
    Returns a format similar to get_aggregated
    """
    cacheable = False

    cols = [
        sql.text("toDate(measurement_start_time) AS measurement_start_day"),
        column("probe_cc"),
        sql.text("countIf(anomaly = 't') AS anomaly_count"),
        sql.text("countIf(confirmed = 't') AS confirmed_count"),
        sql.text("countIf(msm_failure = 't') AS failure_count"),
    ]
    table = sql.table("fastpath")
    where = [sql.text("test_name = 'torsf'")]
    query_params: Dict[str, Any] = {}

    if probe_cc:
        where.append(sql.text("probe_cc = :probe_cc"))
        query_params["probe_cc"] = probe_cc

    if since:
        where.append(sql.text("measurement_start_time > :since"))
        query_params["since"] = since

    if until:
        where.append(sql.text("measurement_start_time <= :until"))
        query_params["until"] = until
        cacheable = until < datetime.now() - timedelta(hours=72)

    # Assemble query
    where_expr = and_(*where)
    query = select(cols).where(where_expr).select_from(table)

    query = query.group_by(column("measurement_start_day"), column("probe_cc"))
    query = query.order_by(column("measurement_start_day"), column("probe_cc"))

    try:
        q = query_click(db, query, query_params)
        result = []
        for row in q:
            row = dict(row)
            row["anomaly_rate"] = row["anomaly_count"] / row["measurement_count"]
            result.append(row)
        if cacheable:
            setcacheresponse("1d", response)
        return Response({"v": 0, "result": result})

    except Exception as e:
        setnocacheresponse(response)
        return ErrorResponse(msg=str(e), v=0)


def get_bucket_url(bucket_name: str) -> str:
    return f"https://{bucket_name}.s3.amazonaws.com/"
