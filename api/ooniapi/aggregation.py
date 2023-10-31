"""
Aggregation API
The routes are mounted under /api
"""

from datetime import datetime, timedelta
from typing import List, Any, Dict
import logging

from flask import Blueprint
from flask import current_app, request, make_response, Response
from flask.json import jsonify

# debdeps: python3-sqlalchemy
from sqlalchemy import and_, select, sql, column

from ooniapi.config import metrics
from ooniapi.database import query_click, query_click_one_row
from ooniapi.utils import jerror, convert_to_csv
from ooniapi.urlparams import (
    commasplit,
    param_asn_m,
    param_date,
    param_domain_m,
    param_input_or_none,
    param_lowercase_underscore,
    param_probe_cc_m,
    param_test_name_m,
    param_uppercase,
)

aggregation_blueprint = Blueprint("aggregation", "measurements")

log = logging.getLogger()


def set_dload(resp, fname: str):
    """Add header to make response downloadable"""
    resp.headers["Content-Disposition"] = f"attachment; filename={fname}"


def group_by_date(since, until, time_grain, cols, colnames, group_by):
    if since and until:
        delta = until - since
    else:
        delta = None

    # on time_grain = "auto" or empty the smallest allowed gran. is used
    ranges = (
        (7, ("hour", "day", "auto")),
        (30, ("day", "week", "auto")),
        (365, ("day", "week", "month", "auto")),
        (9999999, ("day", "week", "month", "year", "auto")),
    )
    if delta is None or delta <= timedelta():
        raise Exception("Invalid since and until values")

    for thresh, allowed in ranges:
        if delta > timedelta(days=thresh):
            continue
        if time_grain not in allowed:
            a = ", ".join(allowed)
            msg = f"Choose time_grain between {a} for the given time range"
            raise Exception(msg)
        if time_grain == "auto":
            time_grain = allowed[0]
        break

    # TODO: check around query weight / response size.
    # Also add support in CSV format.
    gmap = dict(
        hour="toStartOfHour",
        day="toDate",
        week="toStartOfWeek",
        month="toStartOfMonth",
    )
    fun = gmap[time_grain]
    tcol = "measurement_start_day"  # TODO: support dynamic axis names
    cols.append(sql.text(f"{fun}(measurement_start_time) AS {tcol}"))
    colnames.append(tcol)
    group_by.append(column(tcol))
    return time_grain


def validate_axis_name(axis):
    valid = (
        "blocking_type",
        "category_code",
        "domain",
        "input",
        "measurement_start_day",
        "probe_asn",
        "probe_cc",
        "test_name",
    )
    if axis not in valid:
        raise ValueError("Invalid axis name")


def add_axis(axis, cols, colnames, group_by):
    if axis == "blocking_type":
        # TODO: use blocking_type column
        t = "JSONExtractString(scores, 'analysis', 'blocking_type') AS blocking_type"
        cols.append(sql.text(t))
    else:
        validate_axis_name(axis)
        cols.append(sql.text(axis))
    colnames.append(axis)
    group_by.append(column(axis))


@aggregation_blueprint.route("/v1/aggregation")
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
        description: Domain to search measurements for, comma separated
      - name: category_code
        in: query
        type: string
        description: The category code from the citizenlab list
      - name: probe_cc
        in: query
        type: string
        description: Two letter capitalized country codes, comma separated
        minLength: 2
      - name: probe_asn
        in: query
        type: string
        description: Autonomous system number in the format ASxxx, comma separated
      - name: test_name
        in: query
        type: string
        description: Name of the tests, comma separated
      - name: ooni_run_link_id
        in: query
        type: string
        description: OONIRun descriptors comma separated
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
      - name: time_grain
        in: query
        type: string
        description: Time granularity. Used only when the X or Y axis represent time.
        enum:
        - hour
        - day
        - week
        - month
        - year
        - auto
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
    param = request.args.get
    try:
        axis_x = param_lowercase_underscore("axis_x")
        axis_y = param_lowercase_underscore("axis_y")
        category_code = param_uppercase("category_code")
        test_name_s = param_test_name_m("test_name")
        domain_s = param_domain_m()
        inp = param_input_or_none() or ""
        probe_asn_s = param_asn_m()
        probe_cc_s = param_probe_cc_m()
        ooni_run_link_ids_raw = param("ooni_run_link_id")
        since = param_date("since")
        until = param_date("until")
        time_grain = param("time_grain", "auto").lower()

        resp_format = param("format", "JSON").upper()
        download = param("download", "").lower() == "true"
        assert resp_format in ("JSON", "CSV")

        if axis_x is not None:
            assert axis_x != axis_y, "Axis X and Y cannot be the same"

    except Exception as e:
        return jerror(str(e), v=0, code=200)

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
    query_params: Dict[str, Any] = {}

    if domain_s:
        where.append(sql.text("domain IN :domains"))
        query_params["domains"] = domain_s

    if inp:
        where.append(sql.text("input = :input"))
        query_params["input"] = inp

    if category_code:
        where.append(sql.text("citizenlab.category_code = :category_code"))
        query_params["category_code"] = category_code
        if probe_cc_s:
            where.append(sql.text("(citizenlab.cc IN :lccs OR citizenlab.cc = 'ZZ')"))
            query_params["lccs"] = [cc.lower() for cc in probe_cc_s]
        else:
            where.append(sql.text("citizenlab.cc = 'ZZ'"))

    if probe_cc_s:
        where.append(sql.text("probe_cc IN :probe_cc_s"))
        query_params["probe_cc_s"] = probe_cc_s

    if probe_asn_s:
        where.append(sql.text("probe_asn IN :probe_asn_s"))
        query_params["probe_asn_s"] = probe_asn_s

    if ooni_run_link_ids_raw:
        ooni_run_link_ids = commasplit(ooni_run_link_ids_raw)
        where.append(sql.text("ooni_run_link_id IN :ooni_run_link_ids"))
        query_params["ooni_run_link_ids"] = ooni_run_link_ids

    if since:
        where.append(sql.text("measurement_start_time >= :since"))
        query_params["since"] = since

    if until:
        where.append(sql.text("measurement_start_time < :until"))
        query_params["until"] = until

    if test_name_s:
        where.append(sql.text("test_name IN :test_name_s"))
        query_params["test_name_s"] = test_name_s

    group_by: List = []
    try:
        if axis_x == "measurement_start_day":
            group_by_date(since, until, time_grain, cols, colnames, group_by)
        elif axis_x:
            add_axis(axis_x, cols, colnames, group_by)

        if axis_y == "measurement_start_day":
            group_by_date(since, until, time_grain, cols, colnames, group_by)
        elif axis_y:
            add_axis(axis_y, cols, colnames, group_by)

    except Exception as e:
        return jerror(str(e), v=0)

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
            r: Any = list(query_click(query, query_params, query_prio=4))
        else:
            r = query_click_one_row(query, query_params, query_prio=4)

        pq = current_app.click.last_query
        msg = f"Stats: {pq.progress.rows} {pq.progress.bytes} {pq.progress.total_rows} {pq.elapsed}"
        log.info(msg)

        if resp_format == "CSV":
            csv_data = convert_to_csv(r)
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
        return jerror(str(e), v=0)
