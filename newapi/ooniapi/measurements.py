"""
Measurements API
The routes are mounted under /api
"""

from csv import DictWriter
from datetime import datetime, timedelta, date
from dateutil.parser import parse as parse_date
from io import StringIO
from pathlib import Path
from typing import Optional, List, Any
from urllib.parse import urlparse
import gzip
import http.client
import json
import logging
import math
import re
import string
import time

try:
    import lz4framed
except ImportError:
    pass

import ujson  # debdeps: python3-ujson
import urllib3  # debdeps: python3-urllib3

from flask import current_app, request, make_response, abort, redirect, Response
from flask.json import jsonify
from werkzeug.exceptions import HTTPException, BadRequest

# debdeps: python3-sqlalchemy
from sqlalchemy import and_, text, select, sql, column
from sqlalchemy.sql import literal_column
from sqlalchemy import String, cast
from sqlalchemy.exc import OperationalError
from psycopg2.extensions import QueryCanceledError

from urllib.request import urlopen
from urllib.parse import urljoin, urlencode

from ooniapi import __version__
from ooniapi.config import metrics
from ooniapi.utils import cachedjson
from ooniapi.models import TEST_NAMES
from ooniapi.database import query_click, query_click_one_row

from flask import Blueprint

import requests  # debdeps: python3-requests

api_msm_blueprint = Blueprint("msm_api", "measurements")

FASTPATH_MSM_ID_PREFIX = "temp-fid-"
FASTPATH_SERVER = "fastpath.ooni.nu"
FASTPATH_PORT = 8000

log = logging.getLogger()

urllib_pool = urllib3.PoolManager()

# type hints
ostr = Optional[str]

class QueryTimeoutError(HTTPException):
    code = 504
    description = "The database query timed out.\nTry changing the query parameters."


class MsmtNotFound(Exception):
    pass


def get_version():
    return jsonify({"version": __version__})


@api_msm_blueprint.route("/")
def show_apidocs():
    """Route to https://api.ooni.io/api/ to /apidocs/"""
    return redirect("/apidocs")


@api_msm_blueprint.route("/v1/files")
def list_files() -> Response:
    """List files - unsupported"""
    return cachedjson(24, msg="not implemented")


# FIXME respond with help message
@metrics.timer("get_measurement")
@api_msm_blueprint.route("/v1/measurement/<measurement_id>")
def get_measurement(measurement_id, download=None) -> Response:  # pragma: no cover
    """Get one measurement by measurement_id,
    fetching the file from S3 or the fastpath host as needed
    Returns only the measurement without extra data from the database
    fetching the file from the fastpath host
    ---
    parameters:
      - name: measurement_id
        in: path
        required: true
        type: string
        description: The measurement_id to retrieve the measurement for
      - name: download
        in: query
        type: boolean
        description: If we should be triggering a file download
    responses:
      '200':
        description: Returns the JSON blob for the specified measurement
        schema:
          $ref: "#/definitions/MeasurementBlob"
    """
    if not measurement_id.startswith(FASTPATH_MSM_ID_PREFIX):
        raise BadRequest("No measurement found")

    log = current_app.logger
    tid = measurement_id[len(FASTPATH_MSM_ID_PREFIX) :]
    path = "/measurements/{}.json.lz4".format(tid)
    log.info(
        "Incoming fastpath query %r. Fetching %s:%d%s",
        measurement_id,
        FASTPATH_SERVER,
        FASTPATH_PORT,
        path,
    )
    # FIXME
    conn = http.client.HTTPConnection(FASTPATH_SERVER, FASTPATH_PORT)
    conn.request("GET", path)
    r = conn.getresponse()
    log.debug("Response status: %d", r.status)
    try:
        assert r.status == 200
        blob = r.read()
        conn.close()
        log.debug("Decompressing LZ4 data")
        blob = lz4framed.decompress(blob)
        response = make_response(blob)
        response.headers.set("Content-Type", "application/json")
        log.debug("Sending JSON response")
        return response
    except Exception:
        raise BadRequest("No measurement found")


# # Fetching measurement bodies


def _fetch_autoclaved_measurement_body_from_s3(
    autoclaved_fn: str, frame_off: int, frame_size: int, intra_off: int, intra_size: int
) -> bytes:  # pragma: no cover
    """Fetch autoclaved byte range from S3, decompress it"""
    log = current_app.logger
    REQID_HDR = "X-Request-ID"
    # This is the legacy / autoclaved S3 bucket
    BASEURL = "https://ooni-data.s3.amazonaws.com/autoclaved/jsonl.tar.lz4/"
    # Usual size of LZ4 frames is 256kb of decompressed text.
    # Largest size of LZ4 frame was ~55Mb compressed and ~56Mb decompressed.
    url = urljoin(BASEURL, autoclaved_fn)
    range_header = "bytes={}-{}".format(frame_off, frame_off + frame_size - 1)
    hdr = {"Range": range_header}
    log.info(f"Fetching {url} {range_header}")
    r = requests.get(url, headers=hdr)
    r.raise_for_status()
    blob = r.content
    if len(blob) != frame_size:
        raise RuntimeError("Failed to fetch LZ4 frame", len(blob), frame_size)

    blob = lz4framed.decompress(blob)[intra_off : intra_off + intra_size]
    if len(blob) != intra_size or blob[:1] != b"{" or blob[-1:] != b"}":
        raise RuntimeError(
            "Failed to decompress LZ4 frame to measurement.json",
            len(blob),
            intra_size,
            blob[:1],
            blob[-1:],
        )

    return blob


def _fetch_jsonl_measurement_body_inner(
    s3path: str,
    linenum: int,
) -> bytes:
    log = current_app.logger
    # TODO configure from file
    BASEURL = "https://ooni-data-eu-fra.s3.amazonaws.com/"
    url = urljoin(BASEURL, s3path)
    log.info(f"Fetching {url}")
    r = urlopen(url)
    f = gzip.GzipFile(fileobj=r, mode="r")
    for n, line in enumerate(f):
        if n == linenum:
            return line

    raise MsmtNotFound


def _fetch_jsonl_measurement_body_postgresql(
    report_id, input: str, measurement_uid
) -> bytes:  # pragma: no cover
    """Fetch jsonl from S3, decompress it, extract msmt"""
    query = "SELECT s3path, linenum FROM jsonl "
    inp = input or ""  # NULL/None input is stored as ''
    if measurement_uid is None:
        query += "WHERE report_id = :report_id AND input = :inp LIMIT 1"
        query_params = dict(inp=inp, report_id=report_id)

    else:
        query += """WHERE measurement_uid = :mid
        OR (report_id = :rid AND input = :inp)
        LIMIT 1
        """
        query_params = dict(inp=inp, rid=report_id, mid=measurement_uid)

    q = current_app.db_session.execute(query, query_params)
    lookup = q.fetchone()
    if lookup is None:
        m = f"Missing row in jsonl table: {report_id} {input} {measurement_uid}"
        log.error(m)
        raise MsmtNotFound

    s3path = lookup.s3path
    linenum = lookup.linenum
    log.debug(f"Fetching file {s3path} from S3")
    try:
        return _fetch_jsonl_measurement_body_inner(s3path, linenum)
    except:
        log.error(f"Failed to fetch file {s3path} from S3")
        raise MsmtNotFound


@metrics.timer("_fetch_jsonl_measurement_body_clickhouse")
def _fetch_jsonl_measurement_body_clickhouse(
    report_id, input: str, measurement_uid
) -> Optional[bytes]:
    """Fetch jsonl from S3, decompress it, extract msmt"""
    inp = input or ""  # NULL/None input is stored as ''
    try:
        # FIXME temporary hack to test reprocessing
        query = """SELECT s3path, linenum FROM new_jsonl
            PREWHERE report_id = :report_id AND input = :inp
            LIMIT 1"""
        query_params = dict(inp=inp, report_id=report_id)
        lookup = query_click_one_row(sql.text(query), query_params)
        assert lookup is not None
        log.info("Found in new_jsonl")
        metrics.incr("msmt_found_in_new_jsonl")

    except:
        log.info("Not found in new_jsonl")
        metrics.incr("msmt_not_found_in_new_jsonl")
        query = """SELECT s3path, linenum FROM jsonl
            PREWHERE report_id = :report_id AND input = :inp
            LIMIT 1"""
        query_params = dict(inp=inp, report_id=report_id)
        lookup = query_click_one_row(sql.text(query), query_params)

    if lookup is None:
        m = f"Missing row in jsonl table: {report_id} {input} {measurement_uid}"
        log.error(m)
        metrics.incr("msmt_not_found_in_jsonl")
        return None

    s3path = lookup["s3path"]
    linenum = lookup["linenum"]
    log.debug(f"Fetching file {s3path} from S3")
    try:
        return _fetch_jsonl_measurement_body_inner(s3path, linenum)
    except:  # pragma: no cover
        log.error(f"Failed to fetch file {s3path} from S3")
        return None


def _unwrap_post(post: dict) -> dict:
    fmt = post.get("format", "")
    if fmt == "json":
        return post.get("content", {})
    raise Exception("Unexpected format")


def _fetch_measurement_body_on_disk(report_id, input: str) -> Optional[bytes]:
    """Fetch raw POST from disk, extract msmt
    This is used only for msmts that have been processed by the fastpath
    but are not uploaded to S3 yet.
    YAML msmts not supported: requires implementing normalization here
    """
    query = """SELECT measurement_uid
    FROM fastpath
    WHERE report_id = :report_id
    AND measurement_uid LIKE '20%'
    """
    if input is None:
        query += " AND input IS NULL"
    else:
        query += " AND input = :input"
    query_params = dict(input=input, report_id=report_id)
    q = current_app.db_session.execute(query, query_params)
    lookup = q.fetchone()
    if lookup is None:
        log.error(f"Row not found in fastpath table: {report_id} {input}")
        raise Exception

    msmt_uid = lookup.measurement_uid
    if msmt_uid is None:
        # older msmt
        return None
    assert msmt_uid.startswith("20")
    tstamp, cc, testname, hash_ = msmt_uid.split("_")
    hour = tstamp[:10]
    int(hour)
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


def _fetch_autoclaved_measurement_body(
    report_id: str, input
) -> bytes:  # pragma: no cover
    """fetch the measurement body using autoclavedlookup"""
    # uses_pg_index autoclavedlookup_idx
    # None/NULL input needs to be is treated as ""
    query = """SELECT
    frame_off,
    frame_size,
    intra_off,
    intra_size,
    textname,
    filename,
    report_id,
    input
    FROM autoclavedlookup
    WHERE md5(report_id || COALESCE(input, '')) = md5(:report_id || :input)
    """
    query_params = dict(input=(input or ""), report_id=report_id)
    q = current_app.db_session.execute(query, query_params)
    r = q.fetchone()
    if r is None:
        current_app.logger.error(f"missing autoclaved for {report_id} {input}")
        # This is a bug somewhere: the msmt is is the fastpath table and
        # not in the autoclavedlookup table
        raise MsmtNotFound

    body = _fetch_autoclaved_measurement_body_from_s3(
        r.filename, r.frame_off, r.frame_size, r.intra_off, r.intra_size
    )
    return body


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

    for hostname in current_app.config["OTHER_COLLECTORS"]:
        url = urljoin(f"https://{hostname}/measurement_spool", path)
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
def _fetch_measurement_body(report_id, input: str, measurement_uid) -> bytes:
    """Fetch measurement body from either disk, jsonl, measurement spool dir
    on another host or autoclaved on S3"""
    log.debug(f"Fetching body for {report_id} {input}")
    u_count = report_id.count("_")
    # 5: Current format e.g.
    # 20210124T210009Z_webconnectivity_VE_22313_n1_Ojb<redacted>
    new_format = u_count == 5 and measurement_uid

    if new_format:
        ts = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y%m%d%H%M")
        fresh = measurement_uid > ts

    if new_format and fresh:
        body = (
            _fetch_measurement_body_on_disk_by_msmt_uid(measurement_uid)
            or _fetch_measurement_body_from_hosts(measurement_uid)
            or _fetch_jsonl_measurement_body_clickhouse(
                report_id, input, measurement_uid
            )
        )

    elif new_format and not fresh:
        body = (
            _fetch_jsonl_measurement_body_clickhouse(report_id, input, measurement_uid)
            or _fetch_measurement_body_on_disk_by_msmt_uid(measurement_uid)
            or _fetch_measurement_body_from_hosts(measurement_uid)
        )

    else:
        body = _fetch_jsonl_measurement_body_clickhouse(
            report_id, input, measurement_uid
        )

    if body:
        return body

    raise MsmtNotFound


def genurl(path: str, **kw) -> str:
    """Generate absolute URL for the API"""
    base = current_app.config["BASE_URL"]
    return urljoin(base, path) + "?" + urlencode(kw)


@api_msm_blueprint.route("/v1/raw_measurement")
@metrics.timer("get_raw_measurement")
def get_raw_measurement() -> Response:
    """Get raw measurement body by measurement_id + input
    ---
    parameters:
      - name: report_id
        in: query
        type: string
        description: The report_id to search measurements for
      - name: input
        in: query
        type: string
        minLength: 3
        description: The input (for example a URL or IP address) to search measurements for
    responses:
      '200':
        description: raw measurement body, served as JSON file to be dowloaded
    """
    # This is used by Explorer to let users download msmts
    param = request.args.get
    report_id = param("report_id")
    if not report_id or len(report_id) < 15:
        raise BadRequest("Invalid report_id")
    input = param("input")
    body = _fetch_measurement_body(report_id, input, None)
    resp = make_response(body)
    resp.headers.set("Content-Type", "application/json")
    resp.cache_control.max_age = 24 * 3600
    return resp


def _get_measurement_meta_postgresql(
    report_id: str, input_
) -> dict:  # pragma: no cover
    # Given report_id + input, fetch measurement data from fastpath table
    query = """SELECT
        anomaly,
        confirmed,
        msm_failure AS failure,
        input,
        measurement_start_time,
        probe_asn,
        probe_cc,
        report_id,
        measurement_uid,
        CAST(scores AS varchar) AS scores,
        test_name,
        test_start_time
    """
    # fastpath uses input = '' for empty values
    if input_ is None:
        query += """
        FROM fastpath
        WHERE fastpath.report_id = :report_id
        AND (fastpath.input IS NULL or fastpath.input = '')
        AND probe_asn != 0
        """
    else:
        query += """
            , citizenlab.category_code AS category_code
        FROM fastpath
        LEFT OUTER JOIN citizenlab ON citizenlab.url = fastpath.input
        WHERE fastpath.input = :input
        AND fastpath.report_id = :report_id
        AND probe_asn != 0
        """
    query_params = dict(input=input_, report_id=report_id)
    q = current_app.db_session.execute(query, query_params)
    msmt_meta = q.fetchone()
    if msmt_meta is None:
        return {}  # measurement not found

    return dict(msmt_meta)


@metrics.timer("get_measurement_meta_clickhouse")
def _get_measurement_meta_clickhouse(report_id: str, input_) -> dict:
    # Given report_id + input, fetch measurement data from fastpath table
    query = "SELECT * FROM fastpath "
    if input_ is None:
        # fastpath uses input = '' for empty values
        query += "WHERE report_id = :report_id AND input = '' "
    else:
        query += """
        LEFT OUTER JOIN citizenlab ON citizenlab.url = fastpath.input
        WHERE fastpath.input = :input
        AND fastpath.report_id = :report_id
        """
    query_params = dict(input=input_, report_id=report_id)
    # Limit the time range where we scan for the measurement to improve
    # performance
    try:
        rid_t = datetime.strptime(report_id[:8], "%Y%m%d")
        query_params["begin"] = rid_t - timedelta(days=30)
        query_params["end"] = rid_t + timedelta(days=30)
        query += """
        AND fastpath.measurement_start_time > :begin
        AND fastpath.measurement_start_time < :end
        """
    except ValueError:
        pass  # legacy report_id format without date
    except Exception as e:
        log.error(e, exc_info=True)

    query += "LIMIT 1"
    msmt_meta = query_click_one_row(sql.text(query), query_params)
    if not msmt_meta:
        return {}  # measurement not found
    if msmt_meta["probe_asn"] == 0:
        # https://ooni.org/post/2020-ooni-probe-asn-incident-report/
        # https://github.com/ooni/explorer/issues/495
        return {}  # unwanted

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


@api_msm_blueprint.route("/v1/measurement_meta")
@metrics.timer("get_measurement_meta")
def get_measurement_meta() -> Response:
    """Get metadata on one measurement by measurement_id + input
    ---
    produces:
      - application/json
    parameters:
      - name: report_id
        in: query
        type: string
        description: The report_id to search measurements for
        minLength: 3
        required: True
        example: 20210208T162755Z_ndt_DZ_36947_n1_8swgXi7xNuRUyO9a
      - name: input
        in: query
        type: string
        minLength: 3 # `input` is handled by pg_trgm
        description: The input (for example a URL or IP address) to search measurements for
      - name: full
        in: query
        type: boolean
        description: Include JSON measurement data
    responses:
      200:
        description: Returns measurement metadata, optionally including the raw measurement body
        schema:
          type: object
          properties:
            anomaly:
              type: boolean
            category_code:
              type: string
            confirmed:
              type: boolean
            failure:
              type: boolean
            input:
              type: string
            measurement_start_time:
              type: string
            probe_asn:
              type: integer
            probe_cc:
              type: string
            raw_measurement:
              type: string
            report_id:
              type: string
            scores:
              type: string
            test_name:
              type: string
            test_start_time:
              type: string
          example: {
            "anomaly": false,
            "confirmed": false,
            "failure": false,
            "input": null,
            "measurement_start_time": "2021-02-08T23:31:46Z",
            "probe_asn": 36947,
            "probe_cc": "DZ",
            "report_id": "20210208T162755Z_ndt_DZ_36947_n1_8swgXi7xNuRUyO9a",
            "scores": "{}",
            "test_name": "ndt",
            "test_start_time": "2021-02-08T23:31:43Z"
          }
    """

    # TODO: input can be '' or NULL in the fastpath table - fix it
    # TODO: see integ tests for TODO items
    param = request.args.get
    report_id = param("report_id")
    if not report_id or len(report_id) < 15:
        raise BadRequest("Invalid report_id")
    input_ = param("input", None)
    if input_ == "":
        input_ = None

    full = param("full", "").lower() in ("true", "1", "yes")
    log.info(f"get_measurement_meta '{report_id}' '{input_}'")

    if current_app.config["USE_CLICKHOUSE"]:
        msmt_meta = _get_measurement_meta_clickhouse(report_id, input_)
    else:
        msmt_meta = _get_measurement_meta_postgresql(report_id, input_)

    assert isinstance(msmt_meta, dict)
    if not full:
        # FIXME cache timing
        return cachedjson(0, **msmt_meta)

    if msmt_meta == {}:  # measurement not found
        return cachedjson(0, raw_measurement="", **msmt_meta)

    try:
        body = _fetch_measurement_body(report_id, input_, msmt_meta["measurement_uid"])
        assert isinstance(body, bytes)
        body = body.decode()
    except Exception as e:
        log.error(e, exc_info=True)
        body = ""

    # FIXME cache timing
    return cachedjson(0, raw_measurement=body, **msmt_meta)


# # Listing measurements


def _merge_results(tmpresults):
    """Trim list_measurements() outputs that share the same report_id/input"""
    resultsmap = {}
    for r in tmpresults:
        k = (r["report_id"], r["input"])
        if k not in resultsmap:
            resultsmap[k] = r

    return tuple(resultsmap.values())


@api_msm_blueprint.route("/v1/measurements")
@metrics.timer("list_measurements")
def list_measurements() -> Response:
    """Search for measurements using only the database. Provide pagination.
    ---
    parameters:
      - name: report_id
        in: query
        type: string
        description: The report_id to search measurements for
      - name: input
        in: query
        type: string
        minLength: 3 # `input` is handled by pg_trgm
        description: The input (for example a URL or IP address) to search measurements for
      - name: domain
        in: query
        type: string
        minLength: 3
        description: The domain to search measurements for
      - name: probe_cc
        in: query
        type: string
        description: The two letter country code
      - name: probe_asn
        in: query
        type: string
        description: the Autonomous system number in the format "ASXXX"
      - name: test_name
        in: query
        type: string
        description: The name of the test
        enum:
        - bridge_reachability
        - dash
        - dns_consistency
        - dnscheck
        - facebook_messenger
        - http_header_field_manipulation
        - http_host
        - http_invalid_request_line
        - http_requests
        - meek_fronted_requests_test
        - multi_protocol_traceroute
        - ndt
        - psiphon
        - riseupvpn
        - signal
        - stunreachability
        - tcp_connect
        - telegram
        - tor
        - torsf
        - urlgetter
        - vanilla_tor
        - web_connectivity
        - whatsapp
      - name: category_code
        in: query
        type: string
        description: The category code from the citizenlab list
      - name: since
        in: query
        type: string
        description: >-
          The start date of when measurements were run (ex.
          "2016-10-20T10:30:00")
      - name: until
        in: query
        type: string
        description: >-
          The end date of when measurement were run (ex.
          "2016-10-20T10:30:00")
      - name: since_index
        in: query
        type: string
        description: Return results only strictly greater than the provided index

      - name: confirmed
        in: query
        type: string
        collectionFormat: csv
        items:
          type: string
        description: |
          Will be true for confirmed network anomalies (we found a blockpage, a middlebox was found, the IM app is blocked, etc.).

      - name: anomaly
        in: query
        type: string
        collectionFormat: csv
        items:
          type: string
        description: |
          Measurements that require special attention (it's likely to be a case of blocking), however it has not necessarily been confirmed

      - name: failure
        in: query
        type: string
        collectionFormat: csv
        items:
          type: string
        description: |
          There was an error in the measurement (the control request failed, there was a bug, etc.).
          Default is to consider it both true or false (`failure=true,false`)

      - name: order_by
        in: query
        type: string
        description: 'By which key the results should be ordered by (default: `null`)'
        enum:
          - test_start_time
          - measurement_start_time
          - input
          - probe_cc
          - probe_asn
          - test_name
      - name: order
        in: query
        type: string
        description: |-
          If the order should be ascending or descending (one of: `asc` or `desc`)
        enum:
          - asc
          - desc
          - ASC
          - DESC
      - name: offset
        in: query
        type: integer
        description: 'Offset into the result set (default: 0)'
      - name: limit
        in: query
        type: integer
        description: 'Number of records to return (default: 100)'
    responses:
      '200':
        description: Returns the list of measurement IDs for the specified criteria
        schema:
          $ref: "#/definitions/MeasurementList"
    """
    # x-code-samples:
    # - lang: 'curl'
    #    source: |
    #    curl "https://api.ooni.io/api/v1/measurements?probe_cc=IT&confirmed=true&since=2017-09-01"
    # TODO: list_measurements and get_measurement will be simplified and
    # made faster by OOID: https://github.com/ooni/pipeline/issues/48
    log = current_app.logger
    param = request.args.get
    report_id = param("report_id")
    probe_asn = param("probe_asn")
    probe_cc = param("probe_cc")
    test_name = param("test_name")
    since = param_date("since")
    until = param_date("until")
    since_index = param("since_index")  # unused
    order_by = param("order_by")
    order = param("order", "desc")
    offset = int(param("offset", 0))
    limit = int(param("limit", 100))
    failure = param_bool("failure")
    anomaly = param_bool("anomaly")
    confirmed = param_bool("confirmed")
    category_code = param("category_code")

    ## Workaround for https://github.com/ooni/probe/issues/1034
    user_agent = request.headers.get("User-Agent", "")
    if user_agent.startswith("okhttp"):
        bug_probe1034_response = jsonify(
            {
                "metadata": {
                    "count": 1,
                    "current_page": 1,
                    "limit": 100,
                    "next_url": None,
                    "offset": 0,
                    "pages": 1,
                    "query_time": 0.001,
                },
                "results": [{"measurement_url": ""}],
            }
        )
        return bug_probe1034_response

    ## Prepare query parameters

    input_ = request.args.get("input")
    domain = request.args.get("domain")

    if probe_asn is not None:
        if probe_asn.startswith("AS"):
            probe_asn = probe_asn[2:]
        probe_asn = int(probe_asn)

    # Set reasonable since/until ranges if not specified. When looking up by
    # report_id a BTREE is used and since/until are not beneficial.
    try:
        if until is None:
            if report_id is None:
                t = datetime.utcnow() + timedelta(days=1)
                until = datetime(t.year, t.month, t.day)
    except ValueError:
        raise BadRequest("Invalid until")

    try:
        if since is None:
            if report_id is None and until is not None:
                since = until - timedelta(days=30)
    except ValueError:
        raise BadRequest("Invalid since")

    if order.lower() not in ("asc", "desc"):
        raise BadRequest("Invalid order")

    if current_app.config["USE_CLICKHOUSE"]:
        return _list_measurements_click(
            since,
            until,
            report_id,
            probe_cc,
            probe_asn,
            test_name,
            anomaly,
            confirmed,
            failure,
            input_,
            domain,
            category_code,
            order,
            order_by,
            limit,
            offset,
        )
    else:
        return _list_measurements_pg(
            since,
            until,
            report_id,
            probe_cc,
            probe_asn,
            test_name,
            anomaly,
            confirmed,
            failure,
            input_,
            domain,
            category_code,
            order,
            order_by,
            limit,
            offset,
        )


def _list_measurements_pg(
    since,
    until,
    report_id,
    probe_cc,
    probe_asn,
    test_name,
    anomaly,
    confirmed,
    failure,
    input_,
    domain,
    category_code,
    order,
    order_by,
    limit,
    offset,
):
    INULL = ""  # Special value for input = NULL to merge rows with FULL OUTER JOIN

    ## Create fastpath columns for query
    # TODO cast scores, coalesce input as ""
    fpcols = [
        literal_column("measurement_start_time").label("test_start_time"),
        literal_column("measurement_start_time"),
        literal_column("anomaly"),
        literal_column("confirmed"),
        literal_column("msm_failure").label("failure"),
        cast(sql.text("scores"), String).label("scores"),
        literal_column("report_id"),
        literal_column("probe_cc"),
        literal_column("probe_asn"),
        literal_column("test_name"),
        sql.text("coalesce(fastpath.input, '') AS input"),
    ]

    fpwhere = []
    query_params = {}

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
        query_params["probe_cc"] = probe_cc
        fpwhere.append(sql.text("probe_cc = :probe_cc"))

    if probe_asn is not None:
        if probe_asn == 0:
            log.info("Refusing list_measurements with probe_asn set to 0")
            abort(403)
        query_params["probe_asn"] = probe_asn
        fpwhere.append(sql.text("probe_asn = :probe_asn"))
    else:
        fpwhere.append(sql.text("probe_asn != 0"))

    if test_name is not None:
        query_params["test_name"] = test_name
        fpwhere.append(sql.text("test_name = :test_name"))

    # Filter on anomaly, confirmed and failure:
    # The database stores anomaly and confirmed as boolean + NULL and stores
    # failures in different columns. This leads to many possible combinations
    # but only a subset is used.
    # On anomaly and confirmed: any value != TRUE is treated as FALSE
    # See test_list_measurements_filter_flags_fastpath

    if anomaly is True:
        fpwhere.append(sql.text("fastpath.anomaly IS TRUE"))

    elif anomaly is False:
        fpwhere.append(sql.text("fastpath.anomaly IS NOT TRUE"))

    if confirmed is True:
        fpwhere.append(sql.text("fastpath.confirmed IS TRUE"))

    elif confirmed is False:
        fpwhere.append(sql.text("fastpath.confirmed IS NOT TRUE"))

    if failure is True:
        # residual_no is never NULL, msm_failure is always NULL
        fpwhere.append(sql.text("fastpath.msm_failure IS TRUE"))

    elif failure is False:
        # on success measurement.exc is NULL
        fpwhere.append(sql.text("fastpath.msm_failure IS NOT TRUE"))

    fpq_table = sql.table("fastpath")

    if input_:
        # input_ overrides domain and category_code
        query_params["input"] = input_
        fpwhere.append(sql.text("input = :input"))

    elif domain or category_code:
        # both domain and category_code can be set at the same time
        if domain:
            query_params["domain"] = domain
            fpwhere.append(sql.text("domain = :domain"))

        if category_code:
            query_params["category_code"] = category_code
            fpq_table = fpq_table.join(
                sql.table("citizenlab"),
                sql.text("citizenlab.url = :input"),
            )
            fpwhere.append(sql.text("citizenlab.category_code = :category_code"))

    fp_query = select(fpcols).where(and_(*fpwhere)).select_from(fpq_table)
    # .limit(offset + limit)

    # SELECT * FROM fastpath  WHERE measurement_start_time <= '2019-01-01T00:00:00'::timestamp AND probe_cc = 'YT' ORDER BY test_start_time desc   LIMIT 100 OFFSET 0;
    # is using BRIN and running slowly

    if order_by is None:
        # Use test_start_time or measurement_start_time depending on other
        # filters in order to avoid heavy joins.
        # Filtering on anomaly, confirmed, msm_failure -> measurement_start_time
        # Filtering on probe_cc, probe_asn, test_name -> test_start_time
        # See test_list_measurements_slow_order_by_* tests
        if probe_cc or probe_asn or test_name:
            order_by = "test_start_time"
        elif anomaly or confirmed or failure or input_ or domain or category_code:
            order_by = "measurement_start_time"
        else:
            order_by = "measurement_start_time"

    fp_query = fp_query.order_by(text("{} {}".format(order_by, order)))

    # Assemble the "external" query. Run a final order by followed by limit and
    # offset
    query = fp_query.offset(offset).limit(limit)
    query_params["param_1"] = limit
    query_params["param_2"] = offset

    # Run the query, generate the results list
    iter_start_time = time.time()

    # disable bitmapscan otherwise PG uses the BRIN indexes instead of BTREE
    current_app.db_session.execute("SET enable_seqscan=false;")
    try:
        q = current_app.db_session.execute(query, query_params)

        tmpresults = []
        for row in q:
            if row.input in (None, ""):
                url = genurl("/api/v1/raw_measurement", report_id=row.report_id)
            else:
                url = genurl(
                    "/api/v1/raw_measurement", report_id=row.report_id, input=row.input
                )
            tmpresults.append(
                {
                    "measurement_url": url,
                    "report_id": row.report_id,
                    "probe_cc": row.probe_cc,
                    "probe_asn": "AS{}".format(row.probe_asn),
                    "test_name": row.test_name,
                    "measurement_start_time": row.measurement_start_time,
                    "input": row.input,
                    "anomaly": row.anomaly,
                    "confirmed": row.confirmed,
                    "failure": row.failure,
                    "scores": json.loads(row.scores),
                }
            )
    except OperationalError as exc:
        log.error(exc)
        if isinstance(exc.orig, QueryCanceledError):
            # Timeout due to a slow query. Generate metric and do not feed it
            # to Sentry.
            abort(504)

        raise exc

    # For each report_id / input tuple, we want at most one entry.
    results = _merge_results(tmpresults)

    # Replace the special value INULL for "input" with None
    for i, r in enumerate(results):
        if r["input"] == INULL:
            results[i]["input"] = None

    pages = -1
    count = -1
    current_page = math.ceil(offset / limit) + 1

    # We got less results than what we expected, we know the count and that
    # we are done
    if len(tmpresults) < limit:
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
        next_args = request.args.to_dict()
        next_args["offset"] = str(offset + limit)
        next_args["limit"] = str(limit)
        next_url = genurl("/api/v1/measurements", **next_args)

    query_time = time.time() - iter_start_time
    metadata = {
        "offset": offset,
        "limit": limit,
        "count": count,
        "pages": pages,
        "current_page": current_page,
        "next_url": next_url,
        "query_time": query_time,
    }

    return jsonify({"metadata": metadata, "results": results[:limit]})


def _list_measurements_click(
    since,
    until,
    report_id: ostr,
    probe_cc: ostr,
    probe_asn: ostr,
    test_name: ostr,
    anomaly,
    confirmed,
    failure,
    input_: ostr,
    domain: ostr,
    category_code,
    order: ostr,
    order_by,
    limit,
    offset,
) -> Any:
    INULL = ""  # Special value for input = NULL to merge rows with FULL OUTER JOIN

    ## Create fastpath columns for query
    # TODO castscores,   coalesce inputas ""
    fpwhere = []
    query_params = {}

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
        if probe_cc == "ZZ":
            log.info("Refusing list_measurements with probe_cc set to ZZ")
            abort(403)
        query_params["probe_cc"] = probe_cc
        fpwhere.append(sql.text("probe_cc = :probe_cc"))
    else:
        fpwhere.append(sql.text("probe_cc != 'ZZ'"))

    if probe_asn is not None:
        if probe_asn == 0:
            log.info("Refusing list_measurements with probe_asn set to 0")
            abort(403)
        query_params["probe_asn"] = probe_asn
        fpwhere.append(sql.text("probe_asn = :probe_asn"))
    else:
        # https://ooni.org/post/2020-ooni-probe-asn-incident-report/
        # https://github.com/ooni/explorer/issues/495
        fpwhere.append(sql.text("probe_asn != 0"))

    if test_name is not None:
        query_params["test_name"] = test_name
        fpwhere.append(sql.text("test_name = :test_name"))

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
        # residual_no is never NULL, msm_failure is always NULL
        fpwhere.append(sql.text("fastpath.msm_failure = 't'"))

    elif failure is False:
        # on success measurement.exc is NULL
        fpwhere.append(sql.text("fastpath.msm_failure = 'f'"))

    fpq_table = sql.table("fastpath")

    if input_:
        # input_ overrides domain and category_code
        query_params["input"] = input_
        fpwhere.append(sql.text("input = :input"))

    elif domain or category_code:
        # both domain and category_code can be set at the same time
        if domain:
            query_params["domain"] = domain
            fpwhere.append(sql.text("domain = :domain"))

        if category_code:
            query_params["category_code"] = category_code
            fpq_table = fpq_table.join(
                sql.table("citizenlab"),
                sql.text("citizenlab.url = fastpath.input"),
            )
            fpwhere.append(sql.text("citizenlab.category_code = :category_code"))

    fp_query = select("*").where(and_(*fpwhere)).select_from(fpq_table)
    # .limit(offset + limit)

    # SELECT * FROM fastpath  WHERE measurement_start_time <= '2019-01-01T00:00:00'::timestamp AND probe_cc = 'YT' ORDER BY test_start_time desc   LIMIT 100 OFFSET 0;
    # is using BRIN and running slowly

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
        rows = query_click(query, query_params)
        tmpresults = []
        for row in rows:
            if row["input"] in (None, ""):
                url = genurl("/api/v1/raw_measurement", report_id=row["report_id"])
            else:
                url = genurl(
                    "/api/v1/raw_measurement",
                    report_id=row["report_id"],
                    input=row["input"],
                )
            tmpresults.append(
                {
                    "measurement_url": url,
                    "report_id": row["report_id"],
                    "probe_cc": row["probe_cc"],
                    "probe_asn": "AS{}".format(row["probe_asn"]),
                    "test_name": row["test_name"],
                    "measurement_start_time": row["measurement_start_time"],
                    "input": row["input"],
                    "anomaly": row["anomaly"] == "t",
                    "confirmed": row["confirmed"] == "t",
                    "failure": row["msm_failure"] == "t",
                    "scores": json.loads(row["scores"]),
                }
            )
    except OperationalError as exc:
        log.error(exc)
        if isinstance(exc.orig, QueryCanceledError):
            # Timeout due to a slow query. Generate metric and do not feed it
            # to Sentry.
            abort(504)

        raise exc

    # For each report_id / input tuple, we want at most one entry.
    results = _merge_results(tmpresults)

    # Replace the special value INULL for "input" with None
    for i, r in enumerate(results):
        if r["input"] == INULL:
            results[i]["input"] = None

    pages = -1
    count = -1
    current_page = math.ceil(offset / limit) + 1

    # We got less results than what we expected, we know the count and that
    # we are done
    if len(tmpresults) < limit:
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
        next_args = request.args.to_dict()
        next_args["offset"] = str(offset + limit)
        next_args["limit"] = str(limit)
        next_url = genurl("/api/v1/measurements", **next_args)

    query_time = time.time() - iter_start_time
    metadata = {
        "offset": offset,
        "limit": limit,
        "count": count,
        "pages": pages,
        "current_page": current_page,
        "next_url": next_url,
        "query_time": query_time,
    }

    response = jsonify({"metadata": metadata, "results": results[:limit]})
    response.cache_control.max_age = 1
    return response


def _convert_to_csv(r) -> str:
    """Convert aggregation result dict/list to CSV"""
    csvf = StringIO()
    if isinstance(r, dict):
        # 0-dimensional data
        fieldnames = sorted(r.keys())
        writer = DictWriter(csvf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(r)

    else:
        fieldnames = sorted(r[0].keys())
        writer = DictWriter(csvf, fieldnames=fieldnames)
        writer.writeheader()
        for row in r:
            writer.writerow(row)

    result = csvf.getvalue()
    csvf.close()
    return result


def validate(item: ostr, accepted: str) -> None:
    """Ensure item contains only valid chars or is None"""
    if item is None:
        return
    for c in item:
        if c not in accepted:
            raise ValueError("Invalid characters")

# URL parameter parsers

def param_lowercase_underscore(name) -> ostr:
    p = request.args.get(name)
    accepted = string.ascii_lowercase + "_"
    validate(p, accepted)
    return p


def param_uppercase(name) -> ostr:
    p = request.args.get(name)
    validate(p, string.ascii_uppercase)
    return p


def param_asn(name: str) -> Optional[int]:
    p = request.args.get(name)
    if p:
        if p.startswith("AS"):
            return int(p[2:])

        return int(p)

    return None


def param_date(name: str) -> Optional[datetime]:
    p = request.args.get(name)
    if p is None:
        return None
    return parse_date(p)


def param_bool(name: str) -> Optional[bool]:
    p = request.args.get(name)
    if not p:
        return None
    return p.lower() == "true"


domain_matcher = re.compile(
    r"^(?:[a-zA-Z0-9]"  # First char
    r"(?:[a-zA-Z0-9-_]{0,61}[A-Za-z0-9])?\.)"  # sub domain
    r"+[A-Za-z0-9][A-Za-z0-9-_]{0,61}"  # TLD
    r"[A-Za-z]$"  # TLD, last char
)


def validate_domain(p, name):
    try:
        p = p.encode("idna").decode("ascii")
    except:
        raise ValueError(f"Invalid characters in {name} field")
    if not domain_matcher.match(p):
        raise ValueError(f"Invalid characters in {name} field")


def param_domain(name):
    p = request.args.get(name)
    if not p:
        return p
    validate_domain(p, name)
    return p


def param_url(name):
    p = request.args.get(name)
    if not p:
        return p
    url = urlparse(p)
    validate_domain(url.netloc, name)
    return p


@api_msm_blueprint.route("/v1/aggregation")
@metrics.timer("get_aggregated")
def get_aggregated() -> Response:
    """Aggregate counters data
    ---
    parameters:
      - name: input
        in: query
        type: string
        minLength: 3
        description: The input (for example a URL or IP address) to search measurements for
      - name: domain
        in: query
        type: string
        minLength: 3
        description: The domain to search measurements for
      - name: category_code
        in: query
        type: string
        description: The category code from the citizenlab list
      - name: probe_cc
        in: query
        type: string
        description: The two letter country code
        minLength: 2
      - name: probe_asn
        in: query
        type: string
        description: the Autonomous system number in the format "ASXXX"
      - name: test_name
        in: query
        type: string
        description: The name of the test
        enum:
        - bridge_reachability
        - dash
        - dns_consistency
        - dnscheck
        - facebook_messenger
        - http_header_field_manipulation
        - http_host
        - http_invalid_request_line
        - http_requests
        - meek_fronted_requests_test
        - multi_protocol_traceroute
        - ndt
        - psiphon
        - riseupvpn
        - signal
        - stunreachability
        - tcp_connect
        - telegram
        - tor
        - torsf
        - urlgetter
        - vanilla_tor
        - web_connectivity
        - whatsapp
      - name: since
        in: query
        type: string
        description: >-
          The start date of when measurements were run (ex.
          "2016-10-20T10:30:00")
      - name: until
        in: query
        type: string
        description: >-
          The end date of when measurement were run (ex.
          "2016-10-20T10:30:00")
      - name: axis_x
        in: query
        type: string
        description: |
          The dimension on the x axis e.g. measurement_start_day
      - name: axis_y
        in: query
        type: string
        description: |
          The dimension on the y axis e.g. probe_cc
      - name: format
        in: query
        type: string
        description: |
          Output format, JSON (default) or CSV
        enum:
          - JSON
          - CSV
      - name: download
        in: query
        type: boolean
        description: If we should be triggering a file download
    responses:
      '200':
        description: Returns aggregated counters
    """
    # TODO:
    #  better split of large dimensions in output?
    #  add limit and warn user
    log = current_app.logger
    param = request.args.get
    try:
        axis_x = param_lowercase_underscore("axis_x")
        axis_y = param_lowercase_underscore("axis_y")
        category_code = param_uppercase("category_code")
        domain = param_domain("domain")
        inp = param_url("input")
        test_name = param_lowercase_underscore("test_name")
        probe_asn = param_asn("probe_asn")
        probe_cc = param_uppercase("probe_cc")
        since = param_date("since")
        until = param_date("until")
        if test_name and test_name not in TEST_NAMES:
            raise ValueError("Invalid test name")

        resp_format = param("format", "JSON").upper()
        download = (param("download", "").lower() == "true")
        assert resp_format in ("JSON", "CSV")
    except Exception as e:
        return jsonify({"v": 0, "error": str(e)})

    if current_app.config["USE_CLICKHOUSE"]:
        r = _clickhouse_aggregation(
            resp_format,
            download,
            since,
            until,
            inp,
            domain,
            category_code,
            probe_cc,
            probe_asn,
            test_name,
            axis_x,
            axis_y,
        )
        return r

    r = _postgresql_aggregation(
        resp_format,
        since,
        until,
        inp,
        domain,
        category_code,
        probe_cc,
        probe_asn,
        test_name,
        axis_x,
        axis_y,
    )
    return r


def _postgresql_aggregation(
    resp_format,
    since,
    until,
    inp,
    domain,
    category_code,
    probe_cc,
    probe_asn,
    test_name,
    axis_x,
    axis_y,
):  # pragma: no cover

    dimension_cnt = int(bool(axis_x)) + int(bool(axis_y))
    cacheable = until and until < datetime.now() - timedelta(hours=72)

    # Assemble query
    def coalsum(name):
        return sql.text("COALESCE(SUM({0}), 0) AS {0}".format(name))

    cols = [
        coalsum("anomaly_count"),
        coalsum("confirmed_count"),
        coalsum("failure_count"),
        coalsum("measurement_count"),
    ]
    table = sql.table("counters")
    where = []
    query_params = {}

    if domain:
        where.append(sql.text("domain = :domain"))
        query_params["domain"] = domain

    if inp:
        where.append(sql.text("input = :input"))
        query_params["input"] = inp

    if category_code:
        # Join in citizenlab table and filter by category_code
        table = table.join(
            sql.table("citizenlab"),
            sql.text("citizenlab.url = counters.input"),
        )
        where.append(sql.text("category_code = :category_code"))
        query_params["category_code"] = category_code

    if probe_cc:
        where.append(sql.text("probe_cc = :probe_cc"))
        query_params["probe_cc"] = probe_cc

    if probe_asn is not None:
        where.append(sql.text("probe_asn = :probe_asn"))
        query_params["probe_asn"] = probe_asn

    if since:
        where.append(sql.text("measurement_start_day > :since"))
        query_params["since"] = since

    if until:
        where.append(sql.text("measurement_start_day <= :until"))
        query_params["until"] = until

    if test_name:
        assert test_name in TEST_NAMES
        where.append(sql.text("test_name = :test_name"))
        query_params["test_name"] = test_name

    if axis_x:
        # TODO: check if the value is a valid colum name
        cols.append(column(axis_x))
        if axis_x == "category_code":
            # Join in citizenlab table
            table = table.join(
                sql.table("citizenlab"),
                sql.text("citizenlab.url = counters.input"),
            )

    if axis_y:
        # TODO: check if the value is a valid colum name
        if axis_y == "category_code":
            if axis_x != "category_code":
                cols.append(column(axis_y))
                # Join in citizenlab table
                table = table.join(
                    sql.table("citizenlab"),
                    sql.text("citizenlab.url = counters.input"),
                )
        elif axis_y != axis_x:
            # TODO: consider prohibiting axis_x == axis_y ?
            cols.append(column(axis_y))

    # Assemble query
    where_expr = and_(*where)
    query = select(cols).where(where_expr).select_from(table)

    # Add group-by
    if axis_x:
        query = query.group_by(column(axis_x)).order_by(column(axis_x))

    if axis_y and axis_y != axis_x:
        query = query.group_by(column(axis_y)).order_by(column(axis_y))

    try:
        # disable bitmapscan otherwise PG uses the BRIN indexes instead of BTREE
        current_app.db_session.execute("SET enable_seqscan=false;")
        q = current_app.db_session.execute(query, query_params)

        if dimension_cnt == 2:
            r = [dict(row) for row in q]

        elif axis_x or axis_y:
            r = [dict(row) for row in q]

        else:
            r = dict(q.fetchone())

        if resp_format == "CSV":
            return _convert_to_csv(r)

        response = jsonify({"v": 0, "dimension_count": dimension_cnt, "result": r})
        if cacheable:
            response.cache_control.max_age = 3600 * 24
        return response

    except Exception as e:
        return jsonify({"v": 0, "error": str(e)})


def validate_axis_name(axis):
    # TODO: use swagger instead?
    valid = (
        "category_code",
        "input",
        "measurement_start_day",
        "probe_asn",
        "probe_cc",
        "blocking_type",
        "domain",
    )
    if axis not in valid:
        raise ValueError("Invalid axis name")


def set_dload(resp, fname: str):
    """Add header to make response downloadable"""
    resp.headers["Content-Disposition"] = f"attachment; filename={fname}"


def _clickhouse_aggregation(
    resp_format: str,
    download: bool,
    since,
    until,
    inp: ostr,
    domain: ostr,
    category_code: ostr,
    probe_cc: ostr,
    probe_asn: Optional[int],
    test_name: ostr,
    axis_x: ostr,
    axis_y: ostr,
):
    log = current_app.logger
    dimension_cnt = int(bool(axis_x)) + int(bool(axis_y))
    cacheable = until and until < datetime.now() - timedelta(hours=72)
    cacheable = False  # FIXME

    # Assemble query
    colnames = [
        "anomaly_count",
        "confirmed_count",
        "failure_count",
        "ok_count",
        "measurement_count",
    ]
    cols = [
        sql.text(
            "countIf(anomaly = 't' AND confirmed = 'f' AND msm_failure = 'f') AS anomaly_count"
        ),
        sql.text("countIf(confirmed = 't' AND msm_failure = 'f') AS confirmed_count"),
        sql.text("countIf(msm_failure = 't') AS failure_count"),
        sql.text(
            "countIf(anomaly = 'f' AND confirmed = 'f' AND msm_failure = 'f') AS ok_count"
        ),
        sql.text("COUNT(*) AS measurement_count"),
    ]
    table = sql.table("fastpath")
    where = []
    query_params = {}

    if domain:
        where.append(sql.text("domain = :domain"))
        query_params["domain"] = domain

    if inp:
        where.append(sql.text("input = :input"))
        query_params["input"] = inp

    if category_code:
        where.append(sql.text("citizenlab.category_code = :category_code"))
        query_params["category_code"] = category_code
        if probe_cc:
            where.append(sql.text("(citizenlab.cc = :lcc OR citizenlab.cc = 'ZZ')"))
            query_params["lcc"] = probe_cc.lower()
        else:
            where.append(sql.text("citizenlab.cc = 'ZZ'"))

    if probe_cc:
        where.append(sql.text("probe_cc = :probe_cc"))
        query_params["probe_cc"] = probe_cc

    if probe_asn is not None:
        where.append(sql.text("probe_asn = :probe_asn"))
        query_params["probe_asn"] = str(probe_asn)

    if since:
        where.append(sql.text("measurement_start_time > :since"))
        query_params["since"] = since

    if until:
        where.append(sql.text("measurement_start_time <= :until"))
        query_params["until"] = until

    if test_name:
        where.append(sql.text("test_name = :test_name"))
        query_params["test_name"] = test_name

    if axis_x == axis_y and axis_x is not None:
        raise ValueError("Axis X and Y cannot be the same")

    def group_by_date(since, until, cols, colnames, group_by):
        if since and until:
            delta = abs((until - since).days)
        else:
            delta = 0

        # TODO: add a granularity parameter and a check around query weight /
        # / response size. Also add support in CSV format.
        granularity = ("day", "toDate")
        tcol, fun = granularity
        tcol = "measurement_start_day"  # TODO: support dynamic axis names
        cols.append(sql.text(f"{fun}(measurement_start_time) AS {tcol}"))
        colnames.append(tcol)
        group_by.append(column(tcol))

    def add_axis(axis, cols, colnames, group_by):
        if axis == "blocking_type":
            t = "JSONExtractString(scores, 'analysis', 'blocking_type') AS blocking_type"
            cols.append(sql.text(t))
        else:
            validate_axis_name(axis)
            cols.append(sql.text(axis))
        colnames.append(axis)
        group_by.append(column(axis))

    group_by: List = []
    if axis_x == "measurement_start_day":
        group_by_date(since, until, cols, colnames, group_by)
    elif axis_x:
        add_axis(axis_x, cols, colnames, group_by)

    if axis_y == "measurement_start_day":
        group_by_date(since, until, cols, colnames, group_by)
    elif axis_y:
        add_axis(axis_y, cols, colnames, group_by)

    # Assemble query
    if category_code or axis_x == "category_code" or axis_y == "category_code":
        # Join in the citizenlab table if we need to filter on category_code
        # or perform group-by on it
        table = table.join(
            sql.table("citizenlab"),
            sql.text("citizenlab.url = fastpath.input"),
        )

    where_expr = and_(*where)
    query = select(cols).where(where_expr).select_from(table)

    # Add group-by
    for g in group_by:
        query = query.group_by(g).order_by(g)

    try:
        if dimension_cnt > 0:
            r: Any = list(query_click(query, query_params))
        else:
            r = query_click_one_row(query, query_params)

        pq = current_app.click.last_query
        msg = f"Stats: {pq.progress.rows} {pq.progress.bytes} {pq.progress.total_rows} {pq.elapsed}"
        log.info(msg)

        if resp_format == "CSV":
            csv_data = _convert_to_csv(r)
            response = make_response(csv_data)
            response.headers["Content-Type"] = "text/csv"
            if download:
                set_dload(response, "ooni-aggregate-data.csv")

        else:
            resp_d = {
                "v": 0,
                "dimension_count": dimension_cnt,
                "result": r,
                "db_stats": {
                    "row_count": pq.progress.rows,
                    "bytes": pq.progress.bytes,
                    "total_row_count": pq.progress.total_rows,
                    "elapsed_seconds": pq.elapsed,
                },
            }
            response = jsonify(resp_d)
            if download:
                set_dload(response, "ooni-aggregate-data.json")

        if cacheable:
            response.cache_control.max_age = 3600 * 24
        return response

    except Exception as e:
        return jsonify({"v": 0, "error": str(e)})


@api_msm_blueprint.route("/v1/torsf_stats")
@metrics.timer("get_torsf_stats")
def get_torsf_stats() -> Response:
    """Tor Pluggable Transports statistics
    Average / percentiles / total_count grouped by day
    Either group-by or filter by probe_cc
    Returns a format similar to get_aggregated
    ---
    parameters:
      - name: probe_cc
        in: query
        type: string
        description: The two letter country code
        minLength: 2
      - name: since
        in: query
        type: string
        description: >-
          The start date of when measurements were run (ex.
          "2016-10-20T10:30:00")
      - name: until
        in: query
        type: string
        description: >-
          The end date of when measurement were run (ex.
          "2016-10-20T10:30:00")
    responses:
      '200':
        description: Returns aggregated counters
    """
    log = current_app.logger
    param = request.args.get
    probe_cc = param("probe_cc")
    since = param("since")
    until = param("until")
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
    query_params = {}

    if probe_cc:
        where.append(sql.text("probe_cc = :probe_cc"))
        query_params["probe_cc"] = probe_cc

    if since:
        since = parse_date(since)
        where.append(sql.text("measurement_start_time > :since"))
        query_params["since"] = since

    if until:
        until = parse_date(until)
        where.append(sql.text("measurement_start_time <= :until"))
        query_params["until"] = until
        cacheable = until < datetime.now() - timedelta(hours=72)

    # Assemble query
    where_expr = and_(*where)
    query = select(cols).where(where_expr).select_from(table)

    query = query.group_by(column("measurement_start_day"), column("probe_cc"))
    query = query.order_by(column("measurement_start_day"), column("probe_cc"))

    try:
        q = query_click(query, query_params)
        result = []
        for row in q:
            row = dict(row)
            row["anomaly_rate"] = row["anomaly_count"] / row["measurement_count"]
            result.append(row)
        response = jsonify({"v": 0, "result": result})
        if cacheable:
            response.cache_control.max_age = 3600 * 24
        return response

    except Exception as e:
        return jsonify({"v": 0, "error": str(e)})
