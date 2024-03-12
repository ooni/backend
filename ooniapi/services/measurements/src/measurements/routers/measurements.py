"""
Measurements API
The routes are mounted under /api
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Any, Dict, Union
import gzip
import json
import logging
import math
import time

import ujson  # debdeps: python3-ujson
import urllib3  # debdeps: python3-urllib3

from fastapi import APIRouter, Depends, Query, HTTPException, Header, Request
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, validator
from typing_extensions import Annotated

# debdeps: python3-sqlalchemy
from sqlalchemy.sql.expression import and_, text, select, column
from sqlalchemy.sql.expression import text as sql_text
from sqlalchemy.sql.expression import table as sql_table
from sqlalchemy.exc import OperationalError
from psycopg2.extensions import QueryCanceledError  # debdeps: python3-psycopg2

from urllib.request import urlopen
from urllib.parse import urljoin, urlencode

from ..common.config import settings, metrics
from ..common.utils import (
    jerror,
    cachedjson,
    commasplit,
    query_click,
    query_click_one_row,
)
from ..dependencies import ClickhouseClient, get_clickhouse_client

router = APIRouter()

FASTPATH_MSM_ID_PREFIX = "temp-fid-"
FASTPATH_SERVER = "fastpath.ooni.nu"
FASTPATH_PORT = 8000

log = logging.getLogger(__name__)

urllib_pool = urllib3.PoolManager()

# type hints
ostr = Optional[str]


class MsmtNotFound(Exception):
    pass


"""
TODO(art): do we care to have this redirect in place?
@api_msm_blueprint.route("/")
def show_apidocs():
    Route to https://api.ooni.io/api/ to /apidocs/
    return redirect("/apidocs")
"""


@router.get("/v1/files", tags=["files"])
def list_files() -> JSONResponse:
    """List files - unsupported"""
    return cachedjson("1d", msg="not implemented")


def measurement_uid_to_s3path_linenum(db: ClickhouseClient, measurement_uid: str):
    # TODO: cleanup this
    query = """SELECT s3path, linenum FROM jsonl
        PREWHERE (report_id, input) IN (
            SELECT report_id, input FROM fastpath WHERE measurement_uid = :uid
        )
        LIMIT 1"""
    query_params = dict(uid=measurement_uid)
    lookup = query_click_one_row(db, sql_text(query), query_params, query_prio=3)
    if lookup is None:
        raise HTTPException(status_code=500, detail="Measurement not found")

    s3path = lookup["s3path"]
    linenum = lookup["linenum"]
    return s3path, linenum


@metrics.timer("get_measurement")
@router.get("/v1/measurement/{measurement_uid}")
def get_measurement(
    db: Annotated[ClickhouseClient, Depends(get_clickhouse_client)],
    measurement_uid: str,
    download: bool = False,
) -> Response:
    """Get one measurement by measurement_id,
    Returns only the measurement without extra data from the database
    """
    assert measurement_uid
    try:
        s3path, linenum = measurement_uid_to_s3path_linenum(db, measurement_uid)
    except MsmtNotFound:
        return jerror("Incorrect or inexistent measurement_uid")

    log.debug(f"Fetching file {s3path} from S3")
    try:
        body = _fetch_jsonl_measurement_body_from_s3(s3path, linenum)
    except Exception:  # pragma: no cover
        log.error(f"Failed to fetch file {s3path} from S3")
        return jerror("Incorrect or inexistent measurement_uid")

    headers = {"Cache-Control": "max-age=3600"}
    if download:
        headers["Content-Disposition"] = (
            f"attachment; filename=ooni_measurement-{measurement_uid}.json"
        )

    return Response(content=body, media_type="application/json", headers=headers)


# # Fetching measurement bodies


@metrics.timer("_fetch_jsonl_measurement_body_from_s3")
def _fetch_jsonl_measurement_body_from_s3(
    s3path: str,
    linenum: int,
) -> bytes:
    baseurl = f"https://{settings.s3_bucket_name}.s3.amazonaws.com/"
    url = urljoin(baseurl, s3path)
    log.info(f"Fetching {url}")
    r = urlopen(url)
    f = gzip.GzipFile(fileobj=r, mode="r")
    for n, line in enumerate(f):
        if n == linenum:
            return line

    raise MsmtNotFound


def report_id_input_to_s3path_linenum(db: ClickhouseClient, report_id: str, input: str):
    query = """SELECT s3path, linenum FROM jsonl
        PREWHERE report_id = :report_id AND input = :inp
        LIMIT 1"""
    query_params = dict(inp=input, report_id=report_id)
    lookup = query_click_one_row(db, sql_text(query), query_params, query_prio=3)

    if lookup is None:
        m = f"Missing row in jsonl table: {report_id} {input}"
        log.error(m)
        metrics.incr("msmt_not_found_in_jsonl")
        raise MsmtNotFound

    s3path = lookup["s3path"]
    linenum = lookup["linenum"]
    return s3path, linenum


@metrics.timer("_fetch_jsonl_measurement_body_clickhouse")
def _fetch_jsonl_measurement_body_clickhouse(
    db: ClickhouseClient,
    report_id: str,
    input: Optional[str],
    measurement_uid: Optional[str],
) -> Optional[bytes]:
    """
    Fetch jsonl from S3, decompress it, extract single msmt
    """
    # TODO: switch to _fetch_measurement_body_by_uid
    if measurement_uid is not None:
        try:
            s3path, linenum = measurement_uid_to_s3path_linenum(db, measurement_uid)
        except MsmtNotFound:
            log.error(f"Measurement {measurement_uid} not found in jsonl")
            return None

    else:
        inp = input or ""  # NULL/None input is stored as ''
        try:
            s3path, linenum = report_id_input_to_s3path_linenum(db, report_id, inp)
        except Exception:
            log.error(f"Measurement {report_id} {inp} not found in jsonl")
            return None

    try:
        log.debug(f"Fetching file {s3path} from S3")
        # TODO(arturo): remove ignore once https://github.com/jsocol/pystatsd/pull/184 lands
        return _fetch_jsonl_measurement_body_from_s3(s3path, linenum)  # type: ignore
    except Exception:  # pragma: no cover
        log.error(f"Failed to fetch file {s3path} from S3")
        return None


def _unwrap_post(post: dict) -> dict:
    fmt = post.get("format", "")
    if fmt == "json":
        return post.get("content", {})
    raise Exception("Unexpected format")


@metrics.timer("_fetch_measurement_body_on_disk_by_msmt_uid")
def _fetch_measurement_body_on_disk_by_msmt_uid(msmt_uid: str) -> Optional[bytes]:
    """Fetch raw POST from disk, extract msmt
    This is used only for msmts that have been processed by the fastpath
    but are not uploaded to S3 yet.
    YAML msmts not supported: requires implementing normalization here
    """
    assert msmt_uid.startswith("20")
    tstamp, cc, testname, hash_ = msmt_uid.split("_")
    hour = tstamp[:10]
    int(hour)  # raise if the string does not contain an integer
    spooldir = Path("/var/lib/ooniapi/measurements/incoming/")
    postf = spooldir / f"{hour}_{cc}_{testname}/{msmt_uid}.post"
    log.debug(f"Attempt at reading {postf}")
    try:
        with postf.open() as f:
            post = ujson.load(f)
    except FileNotFoundError:
        return None
    body = _unwrap_post(post)
    return ujson.dumps(body).encode()


def _fetch_measurement_body_by_uid(db: ClickhouseClient, msmt_uid: str) -> bytes:
    """Fetch measurement body from either disk or jsonl on S3"""
    log.debug(f"Fetching body for UID {msmt_uid}")
    body = _fetch_measurement_body_on_disk_by_msmt_uid(msmt_uid)
    if body is not None:
        # TODO(arturo): remove ignore once https://github.com/jsocol/pystatsd/pull/184 lands
        return body  # type: ignore

    log.debug(f"Fetching body for UID {msmt_uid} from jsonl on S3")
    s3path, linenum = measurement_uid_to_s3path_linenum(db, msmt_uid)
    return _fetch_jsonl_measurement_body_from_s3(s3path, linenum)  # type: ignore


@metrics.timer("_fetch_measurement_body_from_hosts")
def _fetch_measurement_body_from_hosts(msmt_uid: str) -> Optional[bytes]:
    """Fetch raw POST from another API host, extract msmt
    This is used only for msmts that have been processed by the fastpath
    but are not uploaded to S3 yet.
    """
    try:
        assert msmt_uid.startswith("20")
        tstamp, cc, testname, hash_ = msmt_uid.split("_")
        hour = tstamp[:10]
        int(hour)
        path = f"{hour}_{cc}_{testname}/{msmt_uid}.post"
    except Exception:
        log.info("Error", exc_info=True)
        return None

    for hostname in settings.other_collectors:
        url = urljoin(f"https://{hostname}/measurement_spool/", path)
        log.debug(f"Attempt to load {url}")
        try:
            r = urllib_pool.request("GET", url)
            if r.status == 404:
                log.debug("not found")
                continue
            elif r.status != 200:
                log.error(f"unexpected status {r.status}")
                continue

            post = ujson.loads(r.data)
            body = _unwrap_post(post)
            return ujson.dumps(body).encode()
        except Exception:
            log.info("Error", exc_info=True)
            pass

    return None


@metrics.timer("fetch_measurement_body")
def _fetch_measurement_body(
    db: ClickhouseClient, report_id: str, input: Optional[str], measurement_uid: str
) -> bytes:
    """Fetch measurement body from either:
    - local measurement spool dir (.post files)
    - JSONL files on S3
    - remote measurement spool dir (another API/collector host)
    """
    # TODO: uid_cleanup
    log.debug(f"Fetching body for {report_id} {input}")
    u_count = report_id.count("_")
    # 5: Current format e.g.
    # 20210124T210009Z_webconnectivity_VE_22313_n1_Ojb<redacted>
    new_format = u_count == 5 and measurement_uid

    fresh = False
    if new_format:
        ts = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y%m%d%H%M")
        fresh = measurement_uid > ts

    # Do the fetching in different orders based on the likelyhood of success
    if new_format and fresh:
        body = (
            _fetch_measurement_body_on_disk_by_msmt_uid(measurement_uid)
            or _fetch_measurement_body_from_hosts(measurement_uid)
            or _fetch_jsonl_measurement_body_clickhouse(
                db, report_id, input, measurement_uid
            )
        )

    elif new_format and not fresh:
        body = (
            _fetch_jsonl_measurement_body_clickhouse(
                db, report_id, input, measurement_uid
            )
            or _fetch_measurement_body_on_disk_by_msmt_uid(measurement_uid)
            or _fetch_measurement_body_from_hosts(measurement_uid)
        )

    else:
        body = _fetch_jsonl_measurement_body_clickhouse(
            db, report_id, input, measurement_uid
        )

    if body:
        metrics.incr("msmt_body_found")
        # TODO(arturo): remove ignore once https://github.com/jsocol/pystatsd/pull/184 lands
        return body  # type: ignore

    metrics.incr("msmt_body_not_found")
    raise MsmtNotFound


def genurl(path: str, **kw) -> str:
    """Generate absolute URL for the API"""
    base = settings.base_url
    return urljoin(base, path) + "?" + urlencode(kw)


@router.get("/v1/raw_measurement")
@metrics.timer("get_raw_measurement")
async def get_raw_measurement(
    db: Annotated[ClickhouseClient, Depends(get_clickhouse_client)],
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
) -> Response:
    """Get raw measurement body by report_id + input
    responses:
      '200':
        description: raw measurement body, served as JSON file to be dowloaded
    """
    # This is used by Explorer to let users download msmts
    if measurement_uid:
        # TODO: uid_cleanup
        msmt_meta = _get_measurement_meta_by_uid(db, measurement_uid)
    elif report_id:
        # _fetch_measurement_body needs the UID
        msmt_meta = _get_measurement_meta_clickhouse(db, report_id, input)
    else:
        raise Exception("Either report_id or measurement_uid must be provided")

    body = "{}"
    if msmt_meta:
        # TODO(arturo): remove ignore once https://github.com/jsocol/pystatsd/pull/184 lands
        body = _fetch_measurement_body(
            db, msmt_meta["report_id"], msmt_meta["input"], msmt_meta["measurement_uid"]  # type: ignore
        )

    headers = {"Cache-Control": f"max-age={24*3600}"}
    return Response(content=body, media_type="application/json", headers=headers)


def format_msmt_meta(msmt_meta: dict) -> dict:
    keys = (
        "input",
        "measurement_start_time",
        "measurement_uid",
        "report_id",
        "test_name",
        "test_start_time",
        "probe_asn",
        "probe_cc",
        "scores",
    )
    out = {k: msmt_meta[k] for k in keys}
    out["category_code"] = msmt_meta.get("category_code", None)
    out["anomaly"] = msmt_meta["anomaly"] == "t"
    out["confirmed"] = msmt_meta["confirmed"] == "t"
    out["failure"] = msmt_meta["msm_failure"] == "t"
    return out


@metrics.timer("get_measurement_meta_clickhouse")
def _get_measurement_meta_clickhouse(
    db: ClickhouseClient, report_id: str, input_: Optional[str]
) -> dict:
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
    msmt_meta = query_click_one_row(db, sql_text(query), query_params, query_prio=3)
    if not msmt_meta:
        return {}  # measurement not found
    if msmt_meta["probe_asn"] == 0:
        # https://ooni.org/post/2020-ooni-probe-asn-incident-report/
        # https://github.com/ooni/explorer/issues/495
        return {}  # unwanted

    return format_msmt_meta(msmt_meta)


@metrics.timer("get_measurement_meta_by_uid")
def _get_measurement_meta_by_uid(db: ClickhouseClient, measurement_uid: str) -> dict:
    query = """SELECT * FROM fastpath
        LEFT OUTER JOIN citizenlab ON citizenlab.url = fastpath.input
        WHERE measurement_uid = :uid
        LIMIT 1
    """
    query_params = dict(uid=measurement_uid)
    msmt_meta = query_click_one_row(db, sql_text(query), query_params, query_prio=3)
    if not msmt_meta:
        return {}  # measurement not found
    if msmt_meta["probe_asn"] == 0:
        # https://ooni.org/post/2020-ooni-probe-asn-incident-report/
        # https://github.com/ooni/explorer/issues/495
        return {}  # unwanted

    return format_msmt_meta(msmt_meta)


class MeasurementMeta(BaseModel):
    anomaly: bool
    confirmed: bool
    category_code: str
    failure: bool
    input: str
    probe_asn: int
    probe_cc: str
    raw_measurement: str
    report_id: str
    scores: str
    test_name: str
    test_start_time: datetime


@router.get("/v1/measurement_meta")
@metrics.timer("get_measurement_meta")
async def get_measurement_meta(
    db: Annotated[ClickhouseClient, Depends(get_clickhouse_client)],
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
) -> MeasurementMeta:
    """Get metadata on one measurement by measurement_uid or report_id + input"""

    # TODO: input can be '' or NULL in the fastpath table - fix it
    # TODO: see integ tests for TODO items
    if measurement_uid:
        log.info(f"get_measurement_meta {measurement_uid}")
        msmt_meta = _get_measurement_meta_by_uid(db, measurement_uid)
    elif report_id:
        log.info(f"get_measurement_meta {report_id} {input}")
        msmt_meta = _get_measurement_meta_clickhouse(db, report_id, input)
    else:
        raise Exception("Either report_id or measurement_uid must be provided")

    assert isinstance(msmt_meta, dict)
    if not full:
        response.headers["Cache-Control"] = f"max-age=60"
        return MeasurementMeta(**msmt_meta)

    if msmt_meta == {}:  # measurement not found
        response.headers["Cache-Control"] = f"max-age=60"
        return MeasurementMeta(
            raw_measurement="",
            **msmt_meta,
        )

    try:
        # TODO: uid_cleanup
        body = _fetch_measurement_body(
            db, msmt_meta["report_id"], msmt_meta["input"], msmt_meta["measurement_uid"]
        )
        assert isinstance(body, bytes)
        body = body.decode()
    except Exception as e:
        log.error(e, exc_info=True)
        body = ""

    response.headers["Cache-Control"] = f"max-age=60"
    return MeasurementMeta(
        raw_measurement=body,
        **msmt_meta,
    )


# # Listing measurements


# TODO(art): Isn't this the same as the above MeasurementMeta? Check it
class MeasurementMeta2(BaseModel):
    measurement_url: str
    anomaly: Optional[bool] = None
    confirmed: Optional[bool] = None
    failure: Optional[bool] = None
    input: Optional[str] = None
    measurement_start_time: Optional[datetime] = None
    measurement_uid: Optional[str] = None
    probe_asn: Optional[str] = None
    probe_cc: Optional[str] = None
    report_id: Optional[str] = None
    scores: Optional[dict] = None
    test_name: Optional[str] = None


class ResultsMetadata(BaseModel):
    count: int
    current_page: int
    limit: int
    next_url: Optional[str]
    offset: int
    pages: int
    query_time: float


class MeasurementList(BaseModel):
    metadata: ResultsMetadata
    results: List[MeasurementMeta2]


@router.get("/v1/measurements")
@metrics.timer("list_measurements")
async def list_measurements(
    db: Annotated[ClickhouseClient, Depends(get_clickhouse_client)],
    response: Response,
    request: Request,
    report_id: Annotated[
        Optional[str],
        Query(description="Report_id to search measurements for", min_length=3),
    ] = None,
    input: Annotated[
        Optional[str],
        Query(
            description="Input (for example a URL or IP address) to search measurements for",
            min_length=3,
        ),
    ] = None,
    domain: Annotated[
        Optional[str],
        Query(description="Domain to search measurements for", min_length=3),
    ] = None,
    probe_cc: Annotated[
        Optional[str], Query(description="Two letter country code")
    ] = None,
    probe_asn: Annotated[
        Union[str, int, None],
        Query(description='Autonomous system number in the format "ASXXX"'),
    ] = None,
    test_name: Annotated[Optional[str], Query(description="Name of the test")] = None,
    category_code: Annotated[
        Optional[str], Query(description="Category code from the citizenlab list")
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
) -> MeasurementList:
    """Search for measurements using only the database. Provide pagination."""
    # x-code-samples:
    # - lang: 'curl'
    #    source: |
    #    curl "https://api.ooni.io/api/v1/measurements?probe_cc=IT&confirmed=true&since=2017-09-01"
    if (
        probe_asn is not None
        and isinstance(probe_asn, str)
        and probe_asn.startswith("AS")
    ):
        probe_asn = int(probe_asn[2:])
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
            results=[MeasurementMeta2(measurement_url="")],
        )

    # # Prepare query parameters

    until_dt = None
    if until is not None:
        until_dt = datetime.strptime(until, "%Y-%m-%d")

    # Set reasonable since/until ranges if not specified.
    try:
        if until is None:
            if report_id is None:
                t = datetime.utcnow() + timedelta(days=1)
                until_dt = datetime(t.year, t.month, t.day)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid until")

    since_dt = None
    if since is not None:
        since_dt = datetime.strptime(since, "%Y-%m-%d")

    try:
        if since_dt is None:
            if report_id is None and until_dt is not None:
                since_dt = until_dt - timedelta(days=30)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid since")

    if order.lower() not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="Invalid order")

    # # Perform query

    INULL = ""  # Special value for input = NULL to merge rows with FULL OUTER JOIN

    ## Create fastpath columns for query
    # TODO cast scores, coalesce input as ""
    fpwhere = []
    query_params: Dict[str, Any] = {}

    # Populate WHERE clauses and query_params dict

    if since is not None:
        query_params["since"] = since_dt
        fpwhere.append(sql_text("measurement_start_time > :since"))

    if until is not None:
        query_params["until"] = until_dt
        fpwhere.append(sql_text("measurement_start_time <= :until"))

    if report_id:
        query_params["report_id"] = report_id
        fpwhere.append(sql_text("report_id = :report_id"))

    if probe_cc:
        if probe_cc == "ZZ":
            log.info("Refusing list_measurements with probe_cc set to ZZ")
            raise HTTPException(
                status_code=403,
                detail="Refusing list_measurements with probe_cc set to ZZ",
            )
        query_params["probe_cc"] = probe_cc
        fpwhere.append(sql_text("probe_cc = :probe_cc"))
    else:
        fpwhere.append(sql_text("probe_cc != 'ZZ'"))

    if probe_asn is not None:
        if probe_asn == 0:
            log.info("Refusing list_measurements with probe_asn set to 0")
            raise HTTPException(
                status_code=403,
                detail="Refusing list_measurements with probe_asn set to 0",
            )
        query_params["probe_asn"] = probe_asn
        fpwhere.append(sql_text("probe_asn = :probe_asn"))
    else:
        # https://ooni.org/post/2020-ooni-probe-asn-incident-report/
        # https://github.com/ooni/explorer/issues/495
        fpwhere.append(sql_text("probe_asn != 0"))

    if test_name is not None:
        query_params["test_name"] = test_name
        fpwhere.append(sql_text("test_name = :test_name"))

    if software_versions is not None:
        query_params["software_versions"] = software_versions
        fpwhere.append(sql_text("software_version IN :software_versions"))

    if test_versions is not None:
        query_params["test_versions"] = test_versions
        fpwhere.append(sql_text("test_version IN :test_versions"))

    if engine_versions is not None:
        query_params["engine_versions"] = engine_versions
        fpwhere.append(sql_text("engine_version IN :engine_versions"))

    if ooni_run_link_id is not None:
        query_params["ooni_run_link_id"] = ooni_run_link_id
        fpwhere.append(sql_text("ooni_run_link_id = :ooni_run_link_id"))

    # Filter on anomaly, confirmed and failure:
    # The database stores anomaly and confirmed as boolean + NULL and stores
    # failures in different columns. This leads to many possible combinations
    # but only a subset is used.
    # On anomaly and confirmed: any value != TRUE is treated as FALSE
    # See test_list_measurements_filter_flags_fastpath

    if anomaly is True:
        fpwhere.append(sql_text("fastpath.anomaly = 't'"))

    elif anomaly is False:
        fpwhere.append(sql_text("fastpath.anomaly = 'f'"))

    if confirmed is True:
        fpwhere.append(sql_text("fastpath.confirmed = 't'"))

    elif confirmed is False:
        fpwhere.append(sql_text("fastpath.confirmed = 'f'"))

    if failure is True:
        fpwhere.append(sql_text("fastpath.msm_failure = 't'"))

    elif failure is False:
        fpwhere.append(sql_text("fastpath.msm_failure = 'f'"))

    fpq_table = sql_table("fastpath")

    if input:
        # input_ overrides domain and category_code
        query_params["input"] = input
        fpwhere.append(sql_text("input = :input"))

    elif domain or category_code:
        # both domain and category_code can be set at the same time
        if domain:
            query_params["domain"] = domain
            fpwhere.append(sql_text("domain = :domain"))

        if category_code:
            query_params["category_code"] = category_code
            fpq_table = fpq_table.join(
                sql_table("citizenlab"),
                sql_text("citizenlab.url = fastpath.input"),
            )
            fpwhere.append(sql_text("citizenlab.category_code = :category_code"))

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
            url = genurl("/api/v1/raw_measurement", measurement_uid=msmt_uid)
            results.append(
                MeasurementMeta2(
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
            raise HTTPException(status_code=504)

        raise exc

    # Replace the special value INULL for "input" with None
    for i, r in enumerate(results):
        if r.input == INULL:
            results[i].input = None

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
        next_url = genurl("/api/v1/measurements", **next_args)

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
    response.headers["Cache-Control"] = "max-age=60"
    return MeasurementList(metadata=metadata, results=results[:limit])


@router.get("/v1/torsf_stats")
@metrics.timer("get_torsf_stats")
async def get_torsf_stats(
    db: Annotated[ClickhouseClient, Depends(get_clickhouse_client)],
    response: Response,
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
) -> Response:
    """Tor Pluggable Transports statistics
     Average / percentiles / total_count grouped by day
     Either group-by or filter by probe_cc
     Returns a format similar to get_aggregated
    responses:
       '200':
         description: Returns aggregated counters
    """
    cacheable = False

    table = sql_table("fastpath")
    where = [sql_text("test_name = 'torsf'")]
    query_params: Dict[str, Any] = {}

    if probe_cc:
        where.append(sql_text("probe_cc = :probe_cc"))
        query_params["probe_cc"] = probe_cc

    if since:
        where.append(sql_text("measurement_start_time > :since"))
        query_params["since"] = since

    if until:
        where.append(sql_text("measurement_start_time <= :until"))
        query_params["until"] = until
        cacheable = until < datetime.now() - timedelta(hours=72)

    # Assemble query
    where_expr = and_(*where)
    query = (
        select(
            sql_text("toDate(measurement_start_time) AS measurement_start_day"),
            column("probe_cc"),
            sql_text("countIf(anomaly = 't') AS anomaly_count"),
            sql_text("countIf(confirmed = 't') AS confirmed_count"),
            sql_text("countIf(msm_failure = 't') AS failure_count"),
        )
        .where(where_expr)
        .select_from(table)
    )

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
            response.headers["Cache-Control"] = f"max_age={3600 * 24}"
        return Response({"v": 0, "result": result})

    except Exception as e:
        return jerror(str(e), v=0)
