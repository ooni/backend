import http.client
import json
import math
import re
import time

from dateutil.parser import parse as parse_date

import requests
import lz4framed

from sentry_sdk import configure_scope, capture_exception

from flask import current_app, request, make_response, abort
from flask.json import jsonify
from werkzeug.exceptions import HTTPException, BadRequest

from sqlalchemy import func, and_, false, text, select, sql, column
from sqlalchemy.sql import literal_column
from sqlalchemy import String, cast, Float
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.exc import OperationalError
from psycopg2.extensions import QueryCanceledError

from urllib.parse import urljoin, urlencode

from measurements import __version__
from measurements.config import REPORT_INDEX_OFFSET, REQID_HDR, request_id

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
    log = current_app.logger

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

    cols = [
        literal_column("textname"),
        literal_column("test_start_time"),
        literal_column("probe_cc"),
        literal_column("probe_asn"),
        literal_column("report_no"),
        literal_column("test_name"),
    ]
    where = []
    query_params = {}

    # XXX maybe all of this can go into some sort of function.
    if probe_cc:
        where.append(sql.text("probe_cc = :probe_cc"))
        query_params["probe_cc"] = probe_cc

    if probe_asn:
        where.append(sql.text("probe_asn = :probe_asn"))
        query_params["probe_asn"] = probe_asn

    if test_name:
        where.append(sql.text("test_name = :test_name"))
        query_params["test_name"] = test_name

    if since:
        where.append(sql.text("test_start_time > :since"))
        query_params["since"] = since

    if until:
        where.append(sql.text("test_start_time <= :until"))
        query_params["until"] = until

    if since_index:
        where.append(sql.text("report_no > :report_no"))
        query_params["report_no"] = report_no

    query = select(cols).where(and_(*where)).select_from("report")
    query_cnt = query.with_only_columns([func.count()]).order_by(None)
    log.debug(query_cnt)
    count = current_app.db_session.execute(query_cnt, query_params).scalar()

    pages = math.ceil(count / limit)
    current_page = math.ceil(offset / limit) + 1

    query = query.order_by(text("{} {}".format(order_by, order)))
    query = query.limit(limit).offset(offset)

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

    log.debug(query)
    q = current_app.db_session.execute(query, query_params)
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

    cols = [
        literal_column("measurement.report_no"),
        literal_column("frame_off"),
        literal_column("frame_size"),
        literal_column("intra_off"),
        literal_column("intra_size"),
        literal_column("textname"),
        literal_column("report.autoclaved_no"),
        literal_column("autoclaved.filename"),
    ]
    table = (
        sql.table("measurement")
        .join(
            sql.table("report"), sql.text("measurement.report_no = report.report_no"),
        )
        .join(
            sql.table("autoclaved"),
            sql.text("autoclaved.autoclaved_no = report.autoclaved_no"),
        )
    )
    where = sql.text("measurement.msm_no = :msm_no")
    query = select(cols).where(where).select_from(table)
    query_params = dict(msm_no=msm_no)
    q = current_app.db_session.execute(query, query_params)

    msmt = q.fetchone()
    if msmt is None:
        abort(404)

    # Usual size of LZ4 frames is 256kb of decompressed text.
    # Largest size of LZ4 frame was ~55Mb compressed and ~56Mb decompressed. :-/
    range_header = "bytes={}-{}".format(
        msmt.frame_off, msmt.frame_off + msmt.frame_size - 1
    )
    filename = msmt["autoclaved.filename"]
    r = requests.get(
        urljoin(current_app.config["AUTOCLAVED_BASE_URL"], filename),
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
    order_by=None,
    order="desc",
    offset=0,
    limit=100,
    failure=None,
    anomaly=None,
    confirmed=None,
    category_code=None,
):
    """Search for measurements using only the database. Provide pagination.
    """
    # TODO: list_measurements and get_measurement will be simplified and
    # made faster by OOID: https://github.com/ooni/pipeline/issues/48

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

    ## Create measurement+report colums for SQL query
    cols = [
        # sql.text("measurement.input_no"),
        literal_column("report.test_start_time").label("test_start_time"),
        literal_column("measurement.measurement_start_time").label(
            "measurement_start_time"
        ),
        func.concat(MSM_ID_PREFIX, "-", sql.text("measurement.msm_no")).label(
            "measurement_id"
        ),
        literal_column("measurement.report_no").label("m_report_no"),
        func.coalesce(sql.text("measurement.anomaly"), false()).label("anomaly"),
        func.coalesce(sql.text("measurement.confirmed"), false()).label("confirmed"),
        func.coalesce(sql.text("measurement.msm_failure"), false()).label(
            "msm_failure"
        ),
        func.coalesce("{}").label("scores"),
        literal_column("measurement.exc").label("exc"),
        literal_column("measurement.residual_no").label("residual_no"),
        literal_column("report.report_id").label("report_id"),
        literal_column("report.probe_cc").label("probe_cc"),
        literal_column("report.probe_asn").label("probe_asn"),
        literal_column("report.test_name").label("test_name"),
        literal_column("report.report_no").label("report_no"),
        literal_column("domain_input.input").label("input"),
    ]

    ## Create fastpath columns for query
    fpcols = [
        # func.coalesce(0).label("m_input_no"),
        # We use test_start_time here as the batch pipeline has many NULL measurement_start_times
        literal_column("measurement_start_time").label("test_start_time"),
        literal_column("measurement_start_time").label("measurement_start_time"),
        func.concat(FASTPATH_MSM_ID_PREFIX, sql.text("tid")).label("measurement_id"),
        func.coalesce(
            (cast(cast(sql.text("scores->>'blocking_general'"), String), Float) > 0.5)
        ).label("anomaly"),
        func.coalesce(false()).label("confirmed"),
        cast(sql.text("scores"), String).label("scores"),
        literal_column("report_id"),
        literal_column("probe_cc"),
        literal_column("probe_asn"),
        literal_column("test_name"),
        literal_column("fastpath.input").label("input"),
    ]

    mrwhere = []
    fpwhere = []
    query_params = {}

    # Populate WHERE clauses and query_params dict

    if failure is True:
        # residual_no is never NULL, msm_failure is always NULL
        mrwhere.append(sql.text("measurement.exc IS NOT NULL"))
        # TODO: add failure column to fastpath

    elif failure is False:
        # on success measurement.exc is NULL
        mrwhere.append(sql.text("measurement.exc IS NULL"))

    if since is not None:
        query_params["since"] = since
        mrwhere.append(sql.text("measurement.measurement_start_time > :since"))
        fpwhere.append(sql.text("measurement_start_time > :since"))

    if until is not None:
        query_params["until"] = until
        mrwhere.append(sql.text("measurement.measurement_start_time <= :until"))
        fpwhere.append(sql.text("measurement_start_time <= :until"))

    if report_id:
        query_params["report_id"] = report_id
        mrwhere.append(sql.text("report.report_id = :report_id"))
        fpwhere.append(sql.text("report_id = :report_id"))

    if probe_cc:
        query_params["probe_cc"] = probe_cc
        mrwhere.append(sql.text("report.probe_cc = :probe_cc"))
        fpwhere.append(sql.text("probe_cc = :probe_cc"))

    if probe_asn is not None:
        query_params["probe_asn"] = probe_asn
        mrwhere.append(sql.text("report.probe_asn = :probe_asn"))
        fpwhere.append(sql.text("probe_asn = :probe_asn"))

    if test_name is not None:
        query_params["test_name"] = test_name
        mrwhere.append(sql.text("report.test_name = :test_name"))
        fpwhere.append(sql.text("test_name = :test_name"))

    # TODO, we don't support filtering by confirmed filter in the fastpath, so
    # we exclude all the fastpath measurements when filtering by confirmed is
    # set
    if confirmed is not None:
        query_params["confirmed"] = confirmed
        # TODO: coalesce false() ?
        mrwhere.append(sql.text("measurement.confirmed = :confirmed"))
        fpwhere.append(sql.text("false"))

    if anomaly is not None:
        # TODO: coalesce false() ?
        query_params["anomaly"] = anomaly
        mrwhere.append(sql.text("measurement.anomaly = :anomaly"))
        # fpwhere.append(sql.text("scores->>'blocking_general' > 0.5"))
        fpwhere.append(sql.text("false"))

    fpq_table = sql.table("fastpath")
    mr_table = sql.table("measurement").join(
        sql.table("report"), sql.text("measurement.report_no = report.report_no"),
    )

    if input_ or domain or category_code:
        # join in domain_input
        mr_table = mr_table.join(
            sql.table("domain_input"),
            sql.text("domain_input.input_no = measurement.input_no"),
        )
        fpq_table = fpq_table.join(
            sql.table("domain_input"), sql.text("domain_input.input = fastpath.input")
        )

        if input_:
            # input_ overrides domain and category_code
            query_params["input"] = input_
            mrwhere.append(sql.text("domain_input.input = :input"))
            fpwhere.append(sql.text("domain_input.input = :input"))

        else:
            # both domain and category_code can be set at the same time
            if domain:
                query_params["domain"] = domain
                mrwhere.append(sql.text("domain_input.domain = :domain"))
                fpwhere.append(sql.text("domain_input.domain = :domain"))

            if category_code:
                query_params["category_code"] = category_code
                mr_table = mr_table.join(
                    sql.table("citizenlab"),
                    sql.text("citizenlab.url = domain_input.input"),
                )
                fpq_table = fpq_table.join(
                    sql.table("citizenlab"),
                    sql.text("citizenlab.url = domain_input.input"),
                )
                mrwhere.append(sql.text("citizenlab.category_code = :category_code"))
                fpwhere.append(sql.text("citizenlab.category_code = :category_code"))

    else:
        mr_table = mr_table.outerjoin(
            sql.table("domain_input"),
            sql.text("domain_input.input_no = measurement.input_no"),
        )

    # We runs SELECTs on the measurement-report (mr) tables and faspath independently
    # from each other and then merge them.
    # The FULL OUTER JOIN query is using LIMIT and OFFSET based on the
    # list_measurements arguments. To speed up the two nested queries,
    # an ORDER BY + LIMIT on "limit+offset" is applied in each of them to trim
    # away rows that would be removed anyways by the outer query.
    #
    # During a merge we can find that a measurement is:
    # - only in fastpath:       get_measurement will pick the JSON msmt from the fastpath host
    # - in both selects:        pick `scores` from fastpath and the msmt from the can
    # - only in "mr":           the msmt from the can
    #
    # This implements a failover mechanism where new msmts are loaded from fastpath
    # but can fall back to the traditional pipeline.

    mr_query = (
        select(cols).where(and_(*mrwhere)).select_from(mr_table).limit(offset + limit)
    )
    fp_query = (
        select(fpcols)
        .where(and_(*fpwhere))
        .select_from(fpq_table)
        .limit(offset + limit)
    )

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

    mr_query = mr_query.order_by(text("{} {}".format(order_by, order)))
    fp_query = fp_query.order_by(text("{} {}".format(order_by, order)))

    mr_query = mr_query.alias("mr")
    fp_query = fp_query.alias("fp")

    j = fp_query.join(
        mr_query,
        sql.text("fp.input = mr.input AND fp.report_id = mr.report_id"),
        full=True,
    )

    def coal(colname):
        return func.coalesce(
            literal_column(f"fp.{colname}"), literal_column(f"mr.{colname}")
        ).label(colname)

    merger = [
        coal("test_start_time"),
        coal("measurement_start_time"),
        coal("measurement_id"),
        func.coalesce(literal_column("mr.m_report_no"), 0).label("m_report_no"),
        coal("anomaly"),
        coal("confirmed"),
        func.coalesce(literal_column("fp.scores"), "{}").label("scores"),
        column("exc"),
        func.coalesce(literal_column("mr.residual_no"), 0).label("residual_no"),
        coal("report_id"),
        coal("probe_cc"),
        coal("probe_asn"),
        coal("test_name"),
        coal("input"),
    ]
    # Assemble the "external" query. Run a final order by followed by limit and
    # offset
    fob = text("{} {}".format(order_by, order))
    query = select(merger).select_from(j).order_by(fob).offset(offset).limit(limit)
    log.info(query)

    # Run the query, generate the results list
    iter_start_time = time.time()
    q = current_app.db_session.execute(query, query_params)

    with configure_scope() as scope:
        scope.set_extra("sql_query", query)

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
                        "failure": (row.exc is not None),
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
