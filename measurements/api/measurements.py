import http.client
import json
import math
import re
import time

from dateutil.parser import parse as parse_date

import requests
import lz4framed

from sentry_sdk import configure_scope, capture_exception

from flask import current_app, request, make_response
from flask.json import jsonify
from werkzeug.exceptions import HTTPException, BadRequest

from sqlalchemy.dialects import postgresql
from sqlalchemy import func, or_, and_, false, text, select, sql, column
from sqlalchemy import String, cast, Float
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.exc import OperationalError
from psycopg2.extensions import QueryCanceledError

from urllib.parse import urljoin, urlencode

from measurements import __version__
from measurements.config import REPORT_INDEX_OFFSET, REQID_HDR, request_id
from measurements.models import (
    Autoclaved,
    Domain_input,
    Fastpath,
    Input,
    Measurement,
    Report,
)

MSM_ID_PREFIX = "temp-id"
FASTPATH_MSM_ID_PREFIX = "temp-fid-"
RE_MSM_ID = re.compile("^{}-(\d+)$".format(MSM_ID_PREFIX))
FASTPATH_SERVER = "fastpath.ooni.nu"
FASTPATH_PORT = 8000


class QueryTimeoutError(HTTPException):
    code = 504
    description = (
        "The database query timed out.",
        "Try changing the query parameters.",
    )


def get_version():
    return jsonify({"version": __version__})


def list_files(
    probe_asn=None,
    probe_cc=None,
    test_name=None,
    since=None,
    until=None,
    since_index=None,
    order_by="index",
    order="desc",
    offset=0,
    limit=100,
):

    if probe_asn is not None:
        if probe_asn.startswith("AS"):
            probe_asn = probe_asn[2:]
        probe_asn = int(probe_asn)

    try:
        if since is not None:
            since = parse_date(since)
    except ValueError:
        raise BadRequest("Invalid since")

    try:
        if until is not None:
            until = parse_date(until)
    except ValueError:
        raise BadRequest("Invalid until")

    if since_index is not None:
        since_index = int(since_index)
        report_no = max(0, since_index - REPORT_INDEX_OFFSET)

    if order_by in ("index", "idx"):
        order_by = "report_no"

    q = current_app.db_session.query(
        Report.textname,
        Report.test_start_time,
        Report.probe_cc,
        Report.probe_asn,
        Report.report_no,
        Report.test_name,
    )

    # XXX maybe all of this can go into some sort of function.
    if probe_cc:
        q = q.filter(Report.probe_cc == probe_cc)
    if probe_asn:
        q = q.filter(Report.probe_asn == probe_asn)
    if test_name:
        q = q.filter(Report.test_name == test_name)
    if since:
        q = q.filter(Report.test_start_time > since)
    if until:
        q = q.filter(Report.test_start_time <= until)
    if since_index:
        q = q.filter(Report.report_no > report_no)

    count = q.count()
    pages = math.ceil(count / limit)
    current_page = math.ceil(offset / limit) + 1

    q = q.order_by(text("{} {}".format(order_by, order)))
    q = q.limit(limit).offset(offset)
    next_args = request.args.to_dict()
    next_args["offset"] = "%s" % (offset + limit)
    next_args["limit"] = "%s" % limit
    next_url = urljoin(
        current_app.config["BASE_URL"], "/api/v1/files?%s" % urlencode(next_args)
    )
    if current_page >= pages:
        next_url = None

    metadata = {
        "offset": offset,
        "limit": limit,
        "count": count,
        "pages": pages,
        "current_page": current_page,
        "next_url": next_url,
    }
    results = []
    for row in q:
        download_url = urljoin(
            current_app.config["BASE_URL"], "/files/download/%s" % row.textname
        )
        results.append(
            {
                "download_url": download_url,
                "probe_cc": row.probe_cc,
                "probe_asn": "AS{}".format(row.probe_asn),
                "test_name": row.test_name,
                "index": int(row.report_no) + REPORT_INDEX_OFFSET,
                "test_start_time": row.test_start_time,
            }
        )
    return jsonify({"metadata": metadata, "results": results})


def get_one_fastpath_measurement(measurement_id, download):
    """Get one measurement from the fastpath table by measurement_id,
    fetching the file from the fastpath host
    """
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
    log.debug("Fetching %s:%d %r", FASTPATH_SERVER, FASTPATH_PORT, path)
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


def get_measurement(measurement_id, download=None):
    """Get one measurement by measurement_id,
    fetching the file from S3 or the fastpath host as needed
    Returns only the measurement without extra data from the database
    """
    if measurement_id.startswith(FASTPATH_MSM_ID_PREFIX):
        return get_one_fastpath_measurement(measurement_id, download)

    # XXX this query is slow due to filtering by report_id and input
    # It also occasionally return multiple rows and serves only the first one
    # TODO: add timing metric
    # TODO: switch to OOID to speed up the query
    # https://github.com/ooni/pipeline/issues/48
    m = RE_MSM_ID.match(measurement_id)
    if not m:
        raise BadRequest("Invalid measurement_id")
    msm_no = int(m.group(1))

    q = (
        current_app.db_session.query(
            Measurement.report_no.label("report_no"),
            Measurement.frame_off.label("frame_off"),
            Measurement.frame_size.label("frame_size"),
            Measurement.intra_off.label("intra_off"),
            Measurement.intra_size.label("intra_size"),
            Report.textname.label("textname"),
            Report.report_no.label("r_report_no"),
            Report.autoclaved_no.label("r_autoclaved_no"),
            Autoclaved.filename.label("a_filename"),
            Autoclaved.autoclaved_no.label("a_autoclaved_no"),
        )
        .filter(Measurement.msm_no == msm_no)
        .join(Report, Report.report_no == Measurement.report_no)
        .join(Autoclaved, Autoclaved.autoclaved_no == Report.autoclaved_no)
    )
    try:
        msmt = q.one()
    except MultipleResultsFound:
        current_app.logger.warning(
            "Duplicate rows for measurement_id: %s" % measurement_id
        )
        msmt = q.first()
    except NoResultFound:
        # XXX we should actually return a 404 here
        raise BadRequest("No measurement found")

    # Usual size of LZ4 frames is 256kb of decompressed text.
    # Largest size of LZ4 frame was ~55Mb compressed and ~56Mb decompressed. :-/
    range_header = "bytes={}-{}".format(
        msmt.frame_off, msmt.frame_off + msmt.frame_size - 1
    )
    r = requests.get(
        urljoin(current_app.config["AUTOCLAVED_BASE_URL"], msmt.a_filename),
        headers={"Range": range_header, REQID_HDR: request_id()},
    )
    r.raise_for_status()
    blob = r.content
    if len(blob) != msmt.frame_size:
        raise RuntimeError("Failed to fetch LZ4 frame", len(blob), msmt.frame_size)
    blob = lz4framed.decompress(blob)[msmt.intra_off : msmt.intra_off + msmt.intra_size]
    if len(blob) != msmt.intra_size or blob[:1] != b"{" or blob[-1:] != b"}":
        raise RuntimeError(
            "Failed to decompress LZ4 frame to measurement.json",
            len(blob),
            msmt.intra_size,
            blob[:1],
            blob[-1:],
        )
    # There is no replacement of `measurement_id` with `msm_no` or anything
    # else to keep sanity. Maybe it'll happen as part of orchestration update.
    # Also, blob is not decoded intentionally to save CPU
    filename = "ooni-msmt-{}-{}".format(measurement_id, msmt.textname.replace("/", "-"))
    response = make_response(blob)
    response.headers.set("Content-Type", "application/json")
    if download is not None:
        response.headers.set("Content-Disposition", "attachment", filename=filename)
    return response


def input_cte(input_, domain, test_name):
    """Given a domain or an input_, build a WHERE filter
    """
    if input_ and domain:
        raise BadRequest("Must pick either domain or input")

    if not input_ and not domain:
        return None

    if input_:
        # FIXME: bug on left "%"
        where_or = [text("input.input LIKE :i").bindparams(i="%{}%".format(input_))]
        url_q = (
            select(
                [column("input").label("input"), column("input_no").label("input_no")]
            )
            .where(or_(*where_or))
            .select_from(sql.table("input"))
        )
        return url_q.cte("input_cte")

    # Filter by domain using the domain_input table
    url_q = (
        select([column("input").label("input"), column("input_no").label("input_no")])
        .where(column("domain") == domain)
        .select_from(sql.table("domain_input"))
    )

    return url_q.cte("input_cte")


def log_query(log, q):
    import sqlparse  # debdeps: python3-sqlparse

    sql = str(
        q.statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    sql = sqlparse.format(sql, reindent=True, keyword_case="upper")
    log.info("\n--- query ---\n\n%s\n\n-------------", sql)


def _merge_two_results(a, b):
    """Merge 2 measurements. Collect useful fields from traditional pipeline
    and fastpath
    """
    if a["scores"] and b["scores"]:
        # both a and b are fastpath: ignore b
        return a

    if a["scores"]:
        # merge in useful fields from traditional (b) into a
        for f in ("anomaly", "confirmed"):
            a[f] = b[f]
        return a

    if b["scores"]:
        # merge in useful fields from fastpath (b) into a
        for f in ("scores", "measurement_url", "measurement_id"):
            a[f] = b[f]
        return a

    # both traditional, ignore b
    return a


def _merge_results(tmpresults):
    """Merge list_measurements() outputs from traditional pipeline and fastpath
    """
    resultsmap = {}
    for r in tmpresults:
        k = (r["report_id"], r["input"])
        if k not in resultsmap:
            resultsmap[k] = r
        else:
            resultsmap[k] = _merge_two_results(resultsmap[k], r)

    return tuple(resultsmap.values())


def list_measurements(
    report_id=None,
    probe_asn=None,
    probe_cc=None,
    test_name=None,
    since=None,
    until=None,
    since_index=None,
    order_by="test_start_time",
    order="desc",
    offset=0,
    limit=100,
    failure=None,
    anomaly=None,
    confirmed=None,
):
    """Search for measurements using only the database. Provide pagination.
    """
    # FIXME: list_measurements and get_measurement will be simplified and
    # made faster by https://github.com/ooni/pipeline/issues/48

    log = current_app.logger

    ## Prepare query parameters

    input_ = request.args.get("input")
    domain = request.args.get("domain")

    if probe_asn is not None:
        if probe_asn.startswith("AS"):
            probe_asn = probe_asn[2:]
        probe_asn = int(probe_asn)

    # When the user specifies a list that includes all the possible values for
    # boolean arguments, that is logically the same of applying no filtering at
    # all.
    # TODO: treat it as an error?
    if failure is not None:
        if set(failure) == set(["true", "false"]):
            failure = None
        else:
            failure = set(failure) == set(["true"])
    if anomaly is not None:
        if set(anomaly) == set(["true", "false"]):
            anomaly = None
        else:
            anomaly = set(anomaly) == set(["true"])
    if confirmed is not None:
        if set(confirmed) == set(["true", "false"]):
            confirmed = None
        else:
            confirmed = set(confirmed) == set(["true"])

    try:
        if since is not None:
            since = parse_date(since)
    except ValueError:
        raise BadRequest("Invalid since")

    try:
        if until is not None:
            until = parse_date(until)
    except ValueError:
        raise BadRequest("Invalid until")

    if order.lower() not in ("asc", "desc"):
        raise BadRequest("Invalid order")

    ## Create SQL query
    c_anomaly = func.coalesce(Measurement.anomaly, false()).label("anomaly")
    c_confirmed = func.coalesce(Measurement.confirmed, false()).label("confirmed")
    c_msm_failure = func.coalesce(Measurement.msm_failure, false()).label("msm_failure")
    cols = [
        Measurement.input_no.label("m_input_no"),
        Measurement.measurement_start_time.label("measurement_start_time"),
        Report.test_start_time.label("test_start_time"),
        func.concat(MSM_ID_PREFIX, "-", Measurement.msm_no).label("measurement_id"),
        Measurement.report_no.label("m_report_no"),
        c_anomaly,
        c_confirmed,
        c_msm_failure,
        func.coalesce("{}").label("scores"),
        Measurement.exc.label("exc"),
        Measurement.residual_no.label("residual_no"),
        Report.report_id.label("report_id"),
        Report.probe_cc.label("probe_cc"),
        Report.probe_asn.label("probe_asn"),
        Report.test_name.label("test_name"),
        Report.report_no.label("report_no"),
    ]

    cte = input_cte(input_=input_, domain=domain, test_name=test_name)

    if cte is not None:
        cols.append(cte)
    else:
        cols.append(func.coalesce(Input.input, None).label("input"))

    q = current_app.db_session.query(*cols)
    if cte is not None:
        q = q.join(cte, sql.text("input_cte.input_no = measurement.input_no"))
    else:
        q = q.outerjoin(Input, Measurement.input_no == Input.input_no)
    q = q.join(Report, Report.report_no == Measurement.report_no)

    q.join(Report, Report.report_no == Measurement.report_no)
    if report_id:
        q = q.filter(Report.report_id == report_id)
    if probe_cc:
        q = q.filter(Report.probe_cc == probe_cc)
    if probe_asn is not None:
        q = q.filter(Report.probe_asn == probe_asn)
    if test_name is not None:
        q = q.filter(Report.test_name == test_name)
    if since is not None:
        q = q.filter(Measurement.measurement_start_time > since)
    if until is not None:
        q = q.filter(Measurement.measurement_start_time <= until)

    if confirmed is not None:
        q = q.filter(c_confirmed == confirmed)
    if anomaly is not None:
        q = q.filter(c_anomaly == anomaly)
    if failure is True:
        q = q.filter(
            or_(
                Measurement.exc != None,
                Measurement.residual_no != None,
                c_msm_failure == True,
            )
        )
    if failure is False:
        q = q.filter(
            and_(
                Measurement.exc == None,
                Measurement.residual_no == None,
                c_msm_failure == False,
            )
        )

    ## Create a query for fastpath

    fpcols = [
        func.coalesce(0).label("m_input_no"),
        # We use test_start_time here as the batch pipeline has many NULL measurement_start_times
        sql.text("measurement_start_time as test_start_time"),
        sql.text("measurement_start_time"),
        func.concat(FASTPATH_MSM_ID_PREFIX, sql.text("tid")).label("measurement_id"),
        func.coalesce(0).label("m_report_no"),
        func.coalesce(
            (cast(cast(sql.text("scores->>'blocking_general'"), String), Float) > 0.5)
        ).label("anomaly"),
        func.coalesce(false()).label("confirmed"),
        func.coalesce(false()).label("msm_failure"),
        cast(sql.text("scores"), String),
        func.coalesce([0]).label("exc"),
        func.coalesce(0).label("residual_no"),
        sql.text("report_id"),
        sql.text("probe_cc"),
        sql.text("probe_asn"),
        sql.text("test_name"),
        func.coalesce(0).label("report_no"),
    ]
    if cte is None:
        fpcols.append(sql.text("input"))
        assert len(fpcols) == len(cols)
    else:
        fpcols.append(sql.text("input as input_cte_input"))
        fpcols.append(func.coalesce(0).label("input_cte_input_no"))
        assert len(fpcols) == len(cols) + 1

    where_clause = []
    query_params = {}
    if since is not None:
        query_params["since"] = since
        where_clause.append(sql.text("measurement_start_time > :since"))
    if until is not None:
        query_params["until"] = until
        where_clause.append(sql.text("measurement_start_time <= :until"))
    if report_id:
        query_params["report_id"] = report_id
        where_clause.append(sql.text("report_id = :report_id"))
    if probe_cc:
        query_params["probe_cc"] = probe_cc
        where_clause.append(sql.text("probe_cc = :probe_cc"))
    if probe_asn is not None:
        query_params["probe_asn"] = probe_asn
        where_clause.append(sql.text("probe_asn = :probe_asn"))
    if test_name is not None:
        query_params["test_name"] = test_name
        where_clause.append(sql.text("test_name = :test_name"))

    # TODO, we don't support filtering by confirmed filter in the fastpath, so
    # we exclude all the fastpath measurements when filtering by confirmed is
    # set
    if confirmed is not None:
        where_clause.append(sql.text("false"))
    if anomaly is not None:
        where_clause.append(sql.text("scores->>'blocking_general' > 0.5"))
    # Assemble the query
    if order_by is not None:
        q = q.order_by(text("{} {}".format(order_by, order)))
    q = q.limit(limit).offset(offset)
    # Assemble the query

    fpq_table = sql.table("fastpath")

    if input_:
        query_params["input"] = input_
        where_clause.append(sql.text("input = :input"))
    elif domain:
        query_params["domain"] = input_
        where_clause.append(sql.text("domain = :domain"))
        fpq_table  = fpq_table.join(
                sql.table("domain_input"),
                sql.text("domain_input.input = domain_input.input"),
            )

    s = (
        select(fpcols)
        .where(
            and_(*where_clause)
        )
        .select_from(fpq_table)
    )
    if order_by is not None:
        s = s.order_by(text("{} {}".format(order_by, order)))
    s = s.limit(limit).offset(offset)

    fpq = current_app.db_session.query(s, query_params)
    try:
        q = q.union(fpq)
    except:
        log_query(log, q)
        # log_query(log, fpq)
        raise

    if order_by is not None:
        q = q.order_by(text("{} {}".format(order_by, order)))

    query_str = str(q.statement.compile(dialect=postgresql.dialect()))

    # Run the query, generate the results list
    iter_start_time = time.time()

    with configure_scope() as scope:
        scope.set_extra("sql_query", query_str)

        try:
            tmpresults = []
            for row in q:
                url = urljoin(
                    current_app.config["BASE_URL"],
                    "/api/v1/measurement/%s" % row.measurement_id,
                )
                tmpresults.append(
                    {
                        "measurement_url": url,
                        "measurement_id": row.measurement_id,
                        "report_id": row.report_id,
                        "probe_cc": row.probe_cc,
                        "probe_asn": "AS{}".format(row.probe_asn),
                        "test_name": row.test_name,
                        "measurement_start_time": row.measurement_start_time,
                        "input": row.input,
                        "anomaly": row.anomaly,
                        "confirmed": row.confirmed,
                        "failure": (
                            row.exc != None
                            or row.residual_no != None
                            or row.msm_failure
                        ),
                        "scores": json.loads(row.scores),
                    }
                )
        except OperationalError as exc:
            if isinstance(exc.orig, QueryCanceledError):
                capture_exception(QueryTimeoutError())
                raise QueryTimeoutError()
            raise exc

        # For each report_id / input tuple, we want at most one entry from the
        # traditional pipeline and one from fastpath, merged together
        results = _merge_results(tmpresults)

        pages = -1
        count = -1
        current_page = math.ceil(offset / limit) + 1

        # We got less results than what we expected, we know the count and that we are done
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
            next_args = request.args.to_dict()
            next_args["offset"] = "%s" % (offset + limit)
            next_args["limit"] = "%s" % limit
            next_url = urljoin(
                current_app.config["BASE_URL"],
                "/api/v1/measurements?%s" % urlencode(next_args),
            )

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
