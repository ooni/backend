"""
Measurements API
The routes are mounted under /api
"""

from csv import DictWriter
from datetime import datetime, timedelta, date
from dateutil.parser import parse as parse_date
from io import StringIO
from pathlib import Path
import gzip
import http.client
import json
import logging
import math
import time

# import yaml
import lz4framed

import ujson

from flask import current_app, request, make_response, abort, redirect
from flask.json import jsonify
from werkzeug.exceptions import HTTPException, BadRequest

from sqlalchemy import func, and_, false, text, select, sql, column
from sqlalchemy.sql import literal_column
from sqlalchemy import String, cast
from sqlalchemy.exc import OperationalError
from psycopg2.extensions import QueryCanceledError

from urllib.request import urlopen
from urllib.parse import urljoin, urlencode

from ooniapi import __version__
from ooniapi.config import REPORT_INDEX_OFFSET
from ooniapi.config import metrics
from ooniapi.utils import cachedjson
from ooniapi.models import TEST_NAMES

from flask import Blueprint

import requests

api_msm_blueprint = Blueprint("msm_api", "measurements")

FASTPATH_MSM_ID_PREFIX = "temp-fid-"
FASTPATH_SERVER = "fastpath.ooni.nu"
FASTPATH_PORT = 8000

log = logging.getLogger()


class QueryTimeoutError(HTTPException):
    code = 504
    description = "The database query timed out.\nTry changing the query parameters."


def get_version():
    return jsonify({"version": __version__})


@api_msm_blueprint.route("/")
def show_apidocs():
    """Route to https://api.ooni.io/api/ to /apidocs/"""
    return redirect("/apidocs")


@api_msm_blueprint.route("/v1/files")
def list_files():
    """List files - unsupported"""
    return cachedjson(24, msg="not implemented")


# FIXME respond with help message
@metrics.timer("get_measurement")
@api_msm_blueprint.route("/v1/measurement/<measurement_id>")
def get_measurement(measurement_id, download=None):
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
) -> bytes:
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
    REQID_HDR = "X-Request-ID"
    # TODO configure from file
    BASEURL = "https://ooni-data-eu-fra.s3.amazonaws.com/"
    url = urljoin(BASEURL, s3path)
    log.info(f"Fetching {url}")
    r = urlopen(url)
    f = gzip.GzipFile(fileobj=r, mode="r")
    for n, line in enumerate(f):
        if n == linenum:
            return line

    return b""


def _fetch_jsonl_measurement_body(report_id, input: str) -> bytes:
    """Fetch jsonl from S3, decompress it, extract msmt"""
    query = """SELECT s3path, linenum
    FROM jsonl
    WHERE report_id = :report_id
    AND input = :input
    """
    if input is None:
        input = ""
    query_params = dict(input=input, report_id=report_id)
    q = current_app.db_session.execute(query, query_params)
    lookup = q.fetchone()
    if lookup is None:
        log.error(f"Row not found in jsonl table: {report_id} {input}")
        return b""

    s3path = lookup.s3path
    linenum = lookup.linenum
    if s3path.startswith("raw/") and s3path.endswith(".jsonl.gz"):
        log.error(s3path)
        return _fetch_jsonl_measurement_body_inner(s3path, linenum)

    return b""


def _unwrap_post(post: dict) -> dict:
    fmt = post.get("format", "")
    if fmt == "json":
        return post.get("content", {})
    raise Exception("Unexpected format")


def _fetch_measurement_body_on_disk(report_id, input: str) -> bytes:
    """Fetch raw POST from disk, extract msmt
    This is used only for msmts that have been processed by the fastpath
    but are not uploaded to S3 yet.
    YAML msmts not supported: requires implementing normalization here
    """
    query = """SELECT measurement_uid
    FROM fastpath
    WHERE report_id = :report_id
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
    return ujson.dumps(body)


def _fetch_autoclaved_measurement_body(report_id: str, input) -> dict:
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
        return None

    body = _fetch_autoclaved_measurement_body_from_s3(
        r.filename, r.frame_off, r.frame_size, r.intra_off, r.intra_size
    )
    return body


def _fetch_measurement_body(report_id, input: str) -> bytes:
    """Fetch measurement body from either disk, jsonl or autoclaved on S3"""
    log.debug(f"Fetching body for {report_id} {input}")
    u_count = report_id.count("_")
    # The number of underscores can be:
    # 1: Legacy measurement e.g.
    # 20141101T220015Z_OzDkiPoJMVjHItj<redacted>
    # 2: Legacy measurement e.g.
    # 20201019T050625Z_AS8369_VVqkepmw<redacted>
    # 5: Current format e.g.
    # 20210124T210009Z_webconnectivity_VE_22313_n1_Ojb<redacted>
    if u_count == 5:
        # Look on disk and then from JSONL cans on S3
        body = _fetch_measurement_body_on_disk(report_id, input)
        if body is None:
            log.debug(f"Fetching body for {report_id} {input} from jsonl on S3")
            body = _fetch_jsonl_measurement_body(report_id, input)
    elif u_count == 2:
        body = _fetch_autoclaved_measurement_body(report_id, input)
    elif u_count == 1:
        body = _fetch_autoclaved_measurement_body(report_id, input)
    else:
        raise BadRequest("Invalid report_id")
    return body


def genurl(path: str, **kw) -> str:
    """Generate absolute URL for the API"""
    base = current_app.config["BASE_URL"]
    return urljoin(base, path) + "?" + urlencode(kw)


@api_msm_blueprint.route("/v1/raw_measurement")
@metrics.timer("get_raw_measurement")
def get_raw_measurement():
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
    log = current_app.logger
    param = request.args.get
    report_id = param("report_id")
    if not report_id or len(report_id) < 15:
        raise BadRequest("Invalid report_id")
    input = param("input")
    body = _fetch_measurement_body(report_id, input)
    resp = make_response(body)
    resp.headers.set("Content-Type", "application/json")
    resp.cache_control.max_age = 24 * 3600
    return resp


@api_msm_blueprint.route("/v1/measurement_meta")
@metrics.timer("get_measurement_meta")
def get_measurement_meta():
    """Get metadata on one measurement by measurement_id + input
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
      - name: full
        in: query
        type: boolean
        description: Include JSON measurement data
    responses:
      '200':
        description: Returns measurement metadata, optionally including the raw measurement body
    """

    # TODO: input can be '' or NULL in the fastpath table - fix it
    # TODO: see integ tests for TODO items
    param = request.args.get
    report_id = param("report_id")
    if not report_id or len(report_id) < 15:
        raise BadRequest("Invalid report_id")
    input = param("input", None)
    if input == "":
        input = None

    full = param("full", "").lower() in ("true", "1", "yes")
    log.info(f"get_measurement_meta '{report_id}' '{input}'")

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
        CAST(scores AS varchar) AS scores,
        test_name,
        test_start_time
    """
    # fastpath uses input = '' for empty values
    if input is None:
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
    query_params = dict(input=input, report_id=report_id)
    q = current_app.db_session.execute(query, query_params)
    msmt_meta = q.fetchone()
    if msmt_meta is None:
        # measurement not found
        return jsonify({})

    msmt_meta = dict(msmt_meta)

    if not full:
        return cachedjson(24, **msmt_meta)

    body = _fetch_measurement_body(report_id, input)
    return cachedjson(24, raw_measurement=body, **msmt_meta)


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
def list_measurements():
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
        - web_connectivity
        - http_requests
        - dns_consistency
        - http_invalid_request_line
        - bridge_reachability
        - tcp_connect
        - http_header_field_manipulation
        - http_host
        - multi_protocol_traceroute
        - meek_fronted_requests_test
        - whatsapp
        - vanilla_tor
        - facebook_messenger
        - ndt
        - dash
        - telegram
        - psiphon
        - tor
        - riseupvpn
        - dnscheck
        - urlgetter
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
    since = param("since")
    until = param("until")
    since_index = param("since_index")
    order_by = param("order_by")
    order = param("order", "desc")
    offset = int(param("offset", 0))
    limit = int(param("limit", 100))
    failure = param("failure")
    anomaly = param("anomaly")
    confirmed = param("confirmed")
    category_code = param("category_code")

    ## Workaround for https://github.com/ooni/probe/issues/1034
    user_agent = request.headers.get("User-Agent")
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

    failure = failure and failure.lower() == "true"
    anomaly = anomaly and anomaly.lower() == "true"
    confirmed = confirmed and confirmed.lower() == "true"

    # Set reasonable since/until ranges if not specified. When looking up by
    # report_id a BTREE is used and since/until are not beneficial.
    try:
        if until is None:
            if report_id is None:
                until = date.today() + timedelta(days=1)
        else:
            until = parse_date(until)
    except ValueError:
        raise BadRequest("Invalid until")

    try:
        if since is None:
            if report_id is None and until is not None:
                since = until - timedelta(days=30)
        else:
            since = parse_date(since)
    except ValueError:
        raise BadRequest("Invalid since")

    if order.lower() not in ("asc", "desc"):
        raise BadRequest("Invalid order")

    INULL = ""  # Special value for input = NULL to merge rows with FULL OUTER JOIN

    ## Create fastpath columns for query
    fpcols = [
        # func.coalesce(0).label("m_input_no"),
        # We use test_start_time here as the batch pipeline has many NULL measurement_start_times
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
        func.coalesce(sql.text("fastpath.input"), INULL).label("input"),
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

    fp_query = (
        select(fpcols)
        .where(and_(*fpwhere))
        .select_from(fpq_table)
        .limit(offset + limit)
    )

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


@api_msm_blueprint.route("/v1/aggregation")
@metrics.timer("get_aggregated")
def get_aggregated():
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
        - web_connectivity
        - http_requests
        - dns_consistency
        - http_invalid_request_line
        - bridge_reachability
        - tcp_connect
        - http_header_field_manipulation
        - http_host
        - multi_protocol_traceroute
        - meek_fronted_requests_test
        - whatsapp
        - vanilla_tor
        - facebook_messenger
        - ndt
        - dash
        - telegram
        - psiphon
        - tor
        - riseupvpn
        - dnscheck
        - urlgetter
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
    responses:
      '200':
        description: Returns aggregated counters
    """
    log = current_app.logger
    param = request.args.get
    axis_x = param("axis_x")
    axis_y = param("axis_y")
    category_code = param("category_code")
    domain = param("domain")
    input = param("input")
    test_name = param("test_name")
    probe_asn = param("probe_asn")
    probe_cc = param("probe_cc")
    since = param("since")
    until = param("until")
    format = param("format", "JSON")

    dimension_cnt = int(bool(axis_x)) + int(bool(axis_y))

    cacheable = until and parse_date(until) < datetime.now() - timedelta(hours=72)

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
        if probe_asn.startswith("AS"):
            probe_asn = probe_asn[2:]
        probe_asn = int(probe_asn)
        where.append(sql.text("probe_asn = :probe_asn"))
        query_params["probe_asn"] = probe_asn

    if since:
        since = parse_date(since)
        where.append(sql.text("measurement_start_day > :since"))
        query_params["since"] = since

    if until:
        until = parse_date(until)
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

        if format == "CSV":
            return _convert_to_csv(r)

        response = jsonify({"v": 0, "dimension_count": dimension_cnt, "result": r})
        if cacheable:
            response.cache_control.max_age = 3600 * 24
        return response

    except Exception as e:
        return jsonify({"v": 0, "error": str(e)})


@api_msm_blueprint.route("/private/aggregation")
def aggregation_form():
    """Aggregated counters: HTML page
    ---
    responses:
      '200':
        description: Aggregation form
    """
    html = """
<div>
  <div>
    <form class="form-container">
      <div class="form-item">
        <span class="label">CC</span>
        <input name="probe_cc">
      </div>
      <div class="form-item">
        <span class="label">ASN</span>
        <input name="probe_asn">
      </div>
      <div class="form-item">
        <span class="label">test name</span>
        <input name="test_name" value="web_connectivity">
      </div>
      <div class="form-item">
        <span class="label">domain</span>
        <input name="domain">
      </div>
      <div class="form-item">
        <span class="label">since</span>
        <input name="since" value="2020-05-01">
      </div>
      <div class="form-item">
        <span class="label">until</span>
        <input name="until" value="2020-06-01">
      </div>
      <div class="form-item">
        <span class="label">Category code</span>
        <input name="category_code">
      </div>
      <div class="form-item">
        <span class="label">axis_x</span>
        <select name="axis x">
          <option value="measurement_start_day" selected="">measurement_start_day</option>
          <option value="domain">domain</option>
          <option value="category_code">category_code</option>
          <option value="probe_cc">probe_cc</option>
          <option value="probe_asn">probe_asn</option>
          <option value="">
          </option>
        </select>
      </div>
      <div class="form-item">
        <span class="label">axis y</span>
        <select name="axis_y">
          <option value="measurement_start_day">measurement_start_day</option>
          <option value="domain">domain</option>
          <option value="category_code">category_code</option>
          <option value="probe_cc">probe_cc</option>
          <option value="probe_asn">probe_asn</option>
          <option value="" selected="">
          </option>
        </select>
      </div>
      <input type="submit">
    </form>
  </div>
  <style>
.form-container {
width: 800px;
display: flex;
flex-wrap: wrap;
align-items: center;
}
.form-item .label {
padding-right: 10px;
padding-left: 20px;
}
.form-item {
padding-bottom: 10px;
}
  </style>
  </div>
</div>
        """
    return html
