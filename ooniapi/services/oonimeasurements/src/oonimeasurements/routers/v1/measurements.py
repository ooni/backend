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

from fastapi import (
    APIRouter, 
    Depends, 
    Query, 
    HTTPException, 
    Header, 
    Response, 
    Request
)
from typing_extensions import Annotated

from pydantic import Field

import sqlalchemy as sa
from sqlalchemy import tuple_, Row
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import and_, text, select, column
from sqlalchemy.sql.expression import text as sql_text
from sqlalchemy.sql.expression import table as sql_table
from sqlalchemy.exc import OperationalError
from psycopg2.extensions import QueryCanceledError

from clickhouse_driver import Client as ClickhouseClient

from urllib.request import urlopen
from urllib.parse import urljoin, urlencode

from ... import models

from ...common.config import Settings
from ...common.dependencies import get_settings
from ...common.routers import BaseModel, NotSupportedResponse
from ...common.utils import setcacheresponse, commasplit, setnocacheresponse
from ...common.clickhouse_utils import query_click, query_click_one_row
from ...dependencies import get_clickhouse_session


log = logging.getLogger(__name__)

router = APIRouter()

urllib_pool = urllib3.PoolManager()

MeasurementNotFound = HTTPException(status_code=500, detail="Measurement not found")
ReportInputNotFound = HTTPException(status_code=500, details="Report and input not found")
MeasurementFileNotFound = HTTPException(status_code=404, detail="Measurement S3 file not found")

@router.get(
    "/v1/files", 
    tags=["files"],
    response_model=NotImplemented,
)
def list_files(
    response: Response,
):
    """List files - unsupported"""
    setcacheresponse("1d", response)
    return NotSupportedResponse(msg="not implemented")


def _fetch_jsonl_measurement_body_from_s3(
    s3path: str,
    linenum: int,
    s3_bucket_name: str,
) -> bytes:
    """
    Fetch jsonl from S3, decompress it, extract single msmt 
    """
    baseurl = f"https://{s3_bucket_name}.s3.amazonaws.com/"
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
    response: Response,
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings)
):
    """
    Get one measurement by measurement_id,
    Returns only the measurement without extra data from the database
    """
    assert measurement_uid
    s3path, linenum = measurement_uid_to_s3path_linenum(db, measurement_uid)

    log.debug(f"Fetching file {s3path} from S3")
    body = _fetch_jsonl_measurement_body_from_s3(s3path, linenum, settings.s3_bucket_name)

    if download:
        response.headers["Content-Disposition"] = (
            f"attachment; filename=ooni_measurement-{measurement_uid}.json"
        )

    setcacheresponse("1h", response)
    response.content = body
    response.media_type = "application/json"
    return response


def _unwrap_post(post: dict) -> dict:
    fmt = post.get("format", "")
    if fmt == "json":
        return post.get("content", {})
    raise Exception("Unexpected format")


def _fetch_measurement_body_from_hosts(other_collectors: List[str], measurement_uid: str) -> Optional[bytes]:
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
        url = urljoin(f"https://{hostname}/measurement_spool/", path)
        log.debug(f"Attempt to load {url}")
        try:
            r = urllib_pool.request("GET", url)
            if r.status == 404:
                log.error(f"Measurement {measurement_uid} not found on host {hostname}")
                continue
            elif r.status != 200:
                log.error(f"Unexpected status {r.status} for {measurement_uid} on host {hostname}")
                continue

            post = ujson.loads(r.data)
            body = _unwrap_post(post)
            return ujson.dumps(body).encode()
        except Exception:
            log.info(f"Failed to load fetch {measurement_uid} from {hostname}", exc_info=True)
            pass

    return None


def measurement_uid_to_s3path_linenum(db: Session, measurement_uid: str):
    """
    Fetch measurement S3 location using measurement_uid
    """
    subquery = db.query(models.Fastpath).select(models.Fastpath.report_id, models.Fastpath.input_)
    subquery = subquery.filter(models.Fastpath.measurement_uid == measurement_uid).subquery()

    query = db.query(models.Jsonl).select(models.Jsonl.s3path, models.Jsonl.linenum)
    query = query.filter(tuple_(models.Jsonl.report_id, models.Jsonl.input_).in_(subquery))

    try:
        msmt = query.one()
    except sa.exc.NoResultFound:
        log.error(f"Measurement {measurement_uid} not found in jsonl")
        raise MeasurementNotFound

    return msmt.s3path, msmt.linenum


def _fetch_jsonl_measurement_body_clickhouse(
    db: Session,
    measurement_uid: str,
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
        return _fetch_jsonl_measurement_body_from_s3(s3path, linenum)        
    except Exception as e:
        log.error(f"Failed to fetch {measurement_uid}: {e}", exc_info=True)
        return None


def _fetch_measurement_body(
    db: Session, 
    settings: Settings,
    report_id: str, 
    measurement_uid: str
) -> bytes:
    """
    Fetch measurement body from either:
        - JSONL files on S3
        - remote measurement spool dir (another API/collector host)
    """
    log.debug(f"Fetching body for report_id: {report_id}, measurement_uid: {measurement_uid}")
    
    u_count = report_id.count("_")
    # Current format e.g. 20210124T210009Z_webconnectivity_VE_22313_n1_Ojb<redacted>
    new_format = (u_count == 5 and measurement_uid)

    if not new_format:
        body = _fetch_jsonl_measurement_body_clickhouse(db, measurement_uid)
    else:
        ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y%m%d%H%M")
        fresh = measurement_uid > ts

        # Do the fetching in different orders based on the likelyhood of success
        if new_format and fresh:
            body = (
                _fetch_measurement_body_from_hosts(settings.other_collectors, measurement_uid)
                or _fetch_jsonl_measurement_body_clickhouse(db, measurement_uid)
            )
        elif new_format and not fresh:
            body = (
                _fetch_jsonl_measurement_body_clickhouse(db, measurement_uid)
                or _fetch_measurement_body_from_hosts(settings.other_collectors, measurement_uid)
            )
    if body: 
        return body
    
    raise MeasurementNotFound


class MeasurementMetaFormatted(TypedDict):
    input: str
    measurement_start_time: datetime
    measurement_uid: str
    report_id: str
    test_name: str
    test_start_time: datetime
    probe_asn: str
    probe_cc: str
    scores: str
    category_code: Optional[str]
    anomaly: bool
    confirmed: bool
    failure: bool 


def format_msmt_meta(msmt_meta: Tuple[models.Fastpath, models.Citizenlab]) -> MeasurementMetaFormatted:
    fastpath, citizenlab = msmt_meta
    
    formatted_msmt_meta = MeasurementMetaFormatted(
        input_=fastpath.input_,
        measurement_start_time=fastpath.measurement_start_time,
        measurement_uid=fastpath.measurement_uid,
        report_id=fastpath.report_id,
        test_name=fastpath.test_name,
        test_start_time=fastpath.test_start_time,
        probe_asn=fastpath.probe_asn,
        probe_cc=fastpath.probe_cc,
        scores=fastpath.scores,
        anomaly=(fastpath.anomaly == "t"),
        confirmed=(fastpath.confirmed == "t"),
        failure=(fastpath.failure == "t"),
        category_code=citizenlab.category_code if citizenlab else None,
    )
    return formatted_msmt_meta


def _get_measurement_meta_clickhouse(
    db: Session, report_id: str, input_: Optional[str]
) -> MeasurementMetaFormatted:
    # Given report_id + input, fetch measurement data from fastpath table
    query = db.query(models.Fastpath, models.Citizenlab)
    if input_ is None:
        # fastpath uses input = '' for empty values
        input_ = ''
    else:
        # Join citizenlab to return category_code (useful only for web conn)
        query = query.outerjoin(models.Citizenlab, models.Citizenlab.url == models.Fastpath.input_)
    
    query = query.filter(models.Fastpath.report_id == report_id)
    query = query.filter(models.Fastpath.input_ == input_)
    
    try:
        msmt_meta = query.one()
    except sa.exc.NoResultFound:
        log.error(f"Measurement {report_id}, {input_} not found in fastpath", exc_info=True)
        return {}
    
    if msmt_meta.probe_asn == 0:
        # https://ooni.org/post/2020-ooni-probe-asn-incident-report/
        # https://github.com/ooni/explorer/issues/495
        return {}

    return format_msmt_meta(msmt_meta)


def _get_measurement_meta_by_uid(db: Session, measurement_uid: str) -> MeasurementMetaFormatted:
    """
    Get measurement meta from measurement_uid
    """
    query = db.query(models.Fastpath, models.Citizenlab)
    query = query.outerjoin(models.Citizenlab, models.Fastpath.input_ == models.Citizenlab.url)
    query = query.filter(models.Fastpath.measurement_uid == measurement_uid)

    try:
        msmt_meta = query.one()
    except sa.exc.NoResultFound:
        log.error(f"Measurement {measurement_uid} not found in fastpath", exc_info=True)
        return {}

    if msmt_meta.probe_asn == 0:
        # https://ooni.org/post/2020-ooni-probe-asn-incident-report/
        # https://github.com/ooni/explorer/issues/495
        return {} 

    return format_msmt_meta(msmt_meta)


@router.get("/v1/raw_measurement")
async def get_raw_measurement(
    report_id: Annotated[
        Optional[str],
        Query(description="The report_id to search measurements for", min_length=3),
    ],
    input: Annotated[
        Optional[str],
        Query(
            description="The input (for example a URL or IP address) to search measurements for",
            min_length=3,
        ),
    ],
    measurement_uid: Annotated[
        Optional[str],
        Query(
            description="The measurement_uid to search measurements for", min_length=3
        ),
    ],
    response: Response,
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings),
) -> Response:
    """
    Get raw measurement body
    """
    # This is used by Explorer to let users download msmts
    if measurement_uid:
        log.info(f"get_raw_measurement {measurement_uid}")
        msmt_meta = _get_measurement_meta_by_uid(db, measurement_uid)
    elif report_id:
        log.info(f"get_raw_measurement {report_id} {input}")
        msmt_meta = _get_measurement_meta_clickhouse(db, report_id, input)
    else:
        raise HTTPException(status_code=400, detail="Either report_id or measurement_uid must be provided")

    if msmt_meta:
        body = _fetch_measurement_body(
            db, settings, msmt_meta.report_id, msmt_meta.measurement_uid
        )
    else:
        body = {}

    setcacheresponse("1d", response)
    response.content = body
    response.media_type = "application/json"
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
    input_: Optional[str] = Field(
        default=None, alias="input"
    )
    probe_asn: Optional[int] = Field(
        default=None, title="ASN of the measurement probe"
    )
    probe_cc: Optional[str] = Field(
        default=None, title="country code of the probe ASN"
    )
    report_id: Optional[str] = Field(
        default=None, title="report id of the measurement"
    )
    scores: Optional[str] = Field(
        default=None, title="blocking scores of the measurement"
    )
    test_name: Optional[str] = Field(
        default=None, title="test name of the measurement"
    )


class MeasurementMeta(BaseModel):
    raw_measurement: Optional[str] = Field(
        default=None, title="serialized raw measurement"
    )
    category_code: Optional[str] = Field(
        default=None, title="citizenlab category code of the measurement"
    )
    test_start_time: Optional[datetime] = Field(
        default=None, title="test start time of the measurement"
    )


@router.get("/v1/measurement_meta")
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
    full: Annotated[
        bool, 
        Query(description="Include JSON measurement data")
    ] = False,
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
        raise HTTPException(status_code=400, detail="Either report_id or measurement_uid must be provided")
 
    setcacheresponse("1m", response)
    msmt = MeasurementMeta(
        anomaly=msmt_meta.anomaly,
        confirmed=msmt_meta.confirmed,
        category_code=msmt_meta.category_code,
        failure=msmt_meta.failure,
        input=msmt_meta.input,
        probe_asn=msmt_meta.probe_asn,
        probe_cc=msmt_meta.probe_cc,
        report_id=msmt.report_id,
        scores=msmt_meta.scores,
        test_name=msmt_meta.test_name,
        test_start_time=msmt_meta.test_start_time,
    )
    body = ""
    
    if not full: # return without raw_measurement
        return msmt

    if msmt_meta == {}:  # measurement not found
        return MeasurementMeta(
            raw_measurement=body
        )

    try:
        body = _fetch_measurement_body(
            db, msmt_meta["report_id"], msmt_meta["measurement_uid"]
        )
        assert isinstance(body, bytes)
        body = body.decode()
    except Exception as e:
        log.error(e, exc_info=True)

    msmt.raw_measurement = body
    return msmt


class Measurement(MeasurementBase):
    measurement_url: str = Field(
        title="url of the measurement"
    )
    measurement_start_time: Optional[datetime] = Field(
        default=None, title="start time of the measurement"
    )
    measurement_uid: Optional[str] = Field(
        default=None, title="uid of the measurement"
    )


class ResultsMetadata(BaseModel):
    count: int = Field(
        title=""
    )
    current_page: int = Field(
        title=""
    )
    limit: int = Field(
        title=""
    )
    next_url: Optional[str] = Field(
        title=""
    )
    offset: int = Field(
        title=""
    )
    pages: int = Field(
        title=""
    )
    query_time: float = Field(
        title=""
    )


class MeasurementList(BaseModel):
    metadata: ResultsMetadata = Field(
        title="metadata for query results"
    )
    results: List[Measurement] = Field(
        title="measurement results"
    )


def genurl(base_url: str, path: str, **kw) -> str:
    """Generate absolute URL for the API"""
    return urljoin(base_url, path) + "?" + urlencode(kw)


@router.get("/v1/measurements")
async def list_measurements(
    request: Request,
    response: Response,
    report_id: Annotated[
        Optional[str],
        Query(description="Report_id to search measurements for", min_length=3),
    ],
    input: Annotated[
        Optional[str],
        Query(
            description="Input (for example a URL or IP address) to search measurements for",
            min_length=3,
        ),
    ],
    domain: Annotated[
        Optional[str],
        Query(description="Domain to search measurements for", min_length=3),
    ],
    probe_cc: Annotated[
        Optional[str], Query(description="Two letter country code")
    ],
    probe_asn: Annotated[
        Union[str, int, None],
        Query(description='Autonomous system number in the format "ASXXX"'),
    ],
    test_name: Annotated[
        Optional[str], 
        Query(description="Name of the test"),
    ],
    category_code: Annotated[
        Optional[str], 
        Query(description="Category code from the citizenlab list"),
    ],
    since: Annotated[
        Optional[str],
        Query(
            description='Start date of when measurements were run (ex. "2016-10-20T10:30:00")'
        ),
    ],
    until: Annotated[
        Optional[str],
        Query(
            description='End date of when measurement were run (ex. "2016-10-20T10:30:00")'
        ),
    ],
    confirmed: Annotated[
        Optional[bool],
        Query(
            description=(
                'Set "true" for confirmed network anomalies (we found a blockpage, a middlebox, etc.). '
                "Default: no filtering (show both true and false)"
            )
        ),
    ],
    anomaly: Annotated[
        Optional[bool],
        Query(
            description=(
                'Set "true" for measurements that require special attention (likely to be a case of blocking).'
                "Default: no filtering (show both true and false)"
            )
        ),
    ],
    failure: Annotated[
        Optional[bool],
        Query(
            description=(
                'Set "true" for failed measurements (the control request failed, there was a bug, etc.). '
                "Default: no filtering (show both true and false)"
            )
        ),
    ],
    software_version: Annotated[
        Optional[str],
        Query(description="Filter measurements by software version. Comma-separated."),
    ],
    test_version: Annotated[
        Optional[str],
        Query(description="Filter measurements by test version. Comma-separated."),
    ],
    engine_version: Annotated[
        Optional[str],
        Query(description="Filter measurements by engine version. Comma-separated."),
    ],
    ooni_run_link_id: Annotated[
        Optional[str], Query(description="Filter measurements by OONIRun ID.")
    ],
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
    ],
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

    fpquery = db.query(models.Fastpath)

    if since is not None:
        fpquery = fpquery.where(models.Fastpath.measurement_start_time > since)

    if until is not None:
        fpquery = fpquery.where(models.Fastpath.measurement_start_time <= until)

    if report_id:
        fpquery = fpquery.where(models.Fastpath.report_id == report_id)

    if probe_cc:
        if probe_cc == "ZZ":
            log.info("Refusing list_measurements with probe_cc set to ZZ")
            raise HTTPException(
                status_code=403,
                detail="Refusing list_measurements with probe_cc set to ZZ",
            )
        fpquery = fpquery.where(models.Fastpath.probe_cc == probe_cc)
    else:
        fpquery = fpquery.where(models.Fastpath.probe_cc != "ZZ")

    if probe_asn is not None:
        if probe_asn == 0:
            log.info("Refusing list_measurements with probe_asn set to 0")
            raise HTTPException(
                status_code=403,
                detail="Refusing list_measurements with probe_asn set to 0",
            )
        fpquery = fpquery.where(models.Fastpath.probe_asn == probe_asn)
    else:
        # https://ooni.org/post/2020-ooni-probe-asn-incident-report/
        # https://github.com/ooni/explorer/issues/495
        fpquery = fpquery.where(models.Fastpath.probe_asn != 0)

    if test_name is not None:
        fpquery = fpquery.where(models.Fastpath.test_name == test_name)

    if software_versions is not None:
        fpquery = fpquery.filter(models.Fastpath.software_version.in_(software_versions))

    if test_versions is not None:
        fpquery = fpquery.filter(models.Fastpath.test_version.in_(test_versions))

    if engine_versions is not None:
        fpquery = fpquery.filter(models.Fastpath.engine_version.in_(engine_versions))

    if ooni_run_link_id is not None:
        fpquery = fpquery.where(models.Fastpath.ooni_run_link_id == ooni_run_link_id)

    # Filter on anomaly, confirmed and failure:
    # The database stores anomaly and confirmed as boolean + NULL and stores
    # failures in different columns. This leads to many possible combinations
    # but only a subset is used.
    # On anomaly and confirmed: any value != TRUE is treated as FALSE
    # See test_list_measurements_filter_flags_fastpath

    if anomaly is True:
        fpquery = fpquery.where(models.Fastpath.anomaly == "t")

    elif anomaly is False:
        fpquery = fpquery.where(models.Fastpath.anomaly == "f")

    if confirmed is True:
        fpquery = fpquery.where(models.Fastpath.confirmed == "t")

    elif confirmed is False:
        fpquery = fpquery.where(models.Fastpath.confirmed == "f")

    if failure is True:
        fpquery = fpquery.where(models.Fastpath.msm_failure == "t")

    elif failure is False:
        fpquery = fpquery.where(models.Fastpath.msm_failure == "f")

    if input:
        # input_ overrides domain and category_code
        fpquery = fpquery.where(models.Fastpath.input_ == input)

    elif domain or category_code:
        # both domain and category_code can be set at the same time
        if domain:
            fpquery = fpquery.where(models.Fastpath.domain == domain)

        if category_code:
            fpquery = fpquery.join(models.Citizenlab, models.Citizenlab.url == models.Fastpath.input_)
            fpquery = fpquery.where(models.Citizenlab.category_code == category_code)

    if order_by is None:
        order_by = "measurement_start_time"

    fp_query = fp_query.order_by(text("{} {}".format(order_by, order)))

    # Assemble the "external" query. Run a final order by followed by limit and
    # offset
    fpquery = fpquery.offset(offset).limit(limit)

    # Run the query, generate the results list
    iter_start_time = time.time()

    try:
        rows = fpquery.all()
        results = []
        for row in rows:
            msmt_uid = row.measurement_uid
            url = genurl(settings.base_url, "/api/v1/raw_measurement", measurement_uid=msmt_uid)
            results.append(
                Measurement(
                    measurement_uid=msmt_uid,
                    measurement_url=url,
                    report_id=row.report_id,
                    probe_cc=row.probe_cc,
                    probe_asn="AS{}".format(row.probe_asn),
                    test_name=row.test_name,
                    measurement_start_time=row.measurement_start_time,
                    input=row.input_,
                    anomaly=row.anomaly == "t",  # TODO: This is wrong
                    confirmed=row.confirmed == "t",
                    failure=row.msm_failure == "t",
                    scores=json.loads(row.scores),
                )
            )
    except Exception as exc:
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

    query = db.query(models.Fastpath)
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
            setcacheresponse("1d", response)
        return Response({"v": 0, "result": result})

    except Exception as e:
        setnocacheresponse(response)
        return ErrorResponse(msg=str(e), v=0)
