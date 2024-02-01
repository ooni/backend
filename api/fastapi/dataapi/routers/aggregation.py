"""
Aggregation API
The routes are mounted under /api
"""

from datetime import datetime, timedelta, date
from typing import List, Any, Dict, Optional, Union
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from typing_extensions import Annotated

# debdeps: python3-sqlalchemy
from sqlalchemy.sql.expression import and_, select, column, table
from sqlalchemy.sql.expression import table as sql_table
from sqlalchemy.sql.expression import text as sql_text

from ..config import settings, metrics
from ..utils import (
    jerror,
    convert_to_csv,
    commasplit,
    query_click,
    query_click_one_row,
)
from ..dependencies import ClickhouseClient, get_clickhouse_client

router = APIRouter()

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
    cols.append(sql_text(f"{fun}(measurement_start_time) AS {tcol}"))
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
        cols.append(sql_text(t))
    else:
        validate_axis_name(axis)
        cols.append(sql_text(axis))
    colnames.append(axis)
    group_by.append(column(axis))


class DBStats(BaseModel):
    row_count: int
    bytes: int
    total_row_count: int
    elapsed_seconds: float


class AggregationResult(BaseModel):
    anomaly_count: int
    confirmed_count: int
    failure_count: int
    ok_count: int
    measurement_count: int
    measurement_start_day: Optional[date] = None
    blocking_type: Optional[str] = None
    category_code: Optional[str] = None
    domain: Optional[str] = None
    input: Optional[str] = None
    probe_cc: Optional[str] = None
    probe_asn: Optional[str] = None
    test_name: Optional[str] = None


class MeasurementAggregation(BaseModel):
    v: int
    dimension_count: int
    db_stats: DBStats
    result: List[AggregationResult]


@router.get("/v1/aggregation")
@metrics.timer("get_aggregated")
async def get_measurements(
    db: Annotated[ClickhouseClient, Depends(get_clickhouse_client)],
    response: Response,
    request: Request,
    input: Annotated[
        Optional[str],
        Query(
            min_length=3,
            description="The input (for example a URL or IP address) to search measurements for",
        ),
    ] = None,
    domain: Annotated[
        Optional[str],
        Query(
            min_length=3,
            description="Domain to search measurements for, comma separated",
        ),
    ] = None,
    category_code: Annotated[
        Optional[str],
        Query(
            description="The category code from the citizenlab list",
            regex=r"^[A-Z]+$",
        ),
    ] = None,
    probe_cc: Annotated[
        Optional[str],
        Query(
            min_length=2,
            description="Two letter capitalized country codes, comma separated",
        ),
    ] = None,
    probe_asn: Annotated[
        Optional[str],
        Query(
            description="Autonomous system number in the format ASxxx, comma separated"
        ),
    ] = None,
    test_name: Annotated[
        Optional[str], Query(description="Name of the tests, comma separated")
    ] = None,
    ooni_run_link_id: Annotated[
        Optional[str], Query(description="OONIRun descriptors comma separated")
    ] = None,
    since: Annotated[
        Optional[date],
        Query(
            description="""The start date of when measurements were run (ex. "2016-10-20T10:30:00")"""
        ),
    ] = None,
    until: Annotated[
        Optional[date],
        Query(
            description="""The end date of when measurement were run (ex. "2016-10-20T10:30:00")"""
        ),
    ] = None,
    time_grain: Annotated[
        Optional[str],
        Query(
            description="Time granularity. Used only when the X or Y axis represent time.",
            enum=["hour", "day", "week", "month", "year", "auto"],
        ),
    ] = "auto",
    axis_x: Annotated[
        Optional[str],
        Query(
            description="The dimension on the x axis e.g. measurement_start_day",
            regex=r"^[a-z_]+$",
        ),
    ] = None,
    axis_y: Annotated[
        Optional[str],
        Query(
            description="The dimension on the y axis e.g. probe_cc",
            regex=r"^[a-z_]+$",
        ),
    ] = None,
    format: Annotated[
        str,
        Query(
            description="Output format, JSON (default) or CSV",
            enum=["JSON", "CSV", "json", "csv"],
        ),
    ] = "json",
    download: Annotated[
        Optional[bool], Query(description="If we should be triggering a file download")
    ] = False,
):  # TODO(art): figure out how to define either CSV or JSON data format in the response
    """Aggregate counters data"""
    # TODO:
    #  better split of large dimensions in output?
    #  add limit and warn user
    test_name_s = []
    if test_name:
        test_name_s = commasplit(test_name)
    domain_s = []
    if domain:
        domain_s = set(commasplit(domain))
    probe_asn_s = []
    if probe_asn:
        probe_asn_s = commasplit(probe_asn)
    probe_cc_s = []
    if probe_cc:
        probe_cc_s = commasplit(probe_cc)

    if since:
        since = datetime.combine(since, datetime.min.time())
    if until:
        until = datetime.combine(until, datetime.min.time())

    inp = input or ""
    try:
        ooni_run_link_id_raw = ooni_run_link_id
        resp_format = format.upper()
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
        sql_text(
            "countIf(anomaly = 't' AND confirmed = 'f' AND msm_failure = 'f') AS anomaly_count"
        ),
        sql_text("countIf(confirmed = 't' AND msm_failure = 'f') AS confirmed_count"),
        sql_text("countIf(msm_failure = 't') AS failure_count"),
        sql_text(
            "countIf(anomaly = 'f' AND confirmed = 'f' AND msm_failure = 'f') AS ok_count"
        ),
        sql_text("COUNT(*) AS measurement_count"),
    ]
    table = sql_table("fastpath")
    where = []
    query_params: Dict[str, Any] = {}

    if domain_s:
        where.append(sql_text("domain IN :domains"))
        query_params["domains"] = domain_s

    if inp:
        where.append(sql_text("input = :input"))
        query_params["input"] = inp

    if category_code:
        where.append(sql_text("citizenlab.category_code = :category_code"))
        query_params["category_code"] = category_code
        if probe_cc_s:
            where.append(sql_text("(citizenlab.cc IN :lccs OR citizenlab.cc = 'ZZ')"))
            query_params["lccs"] = [cc.lower() for cc in probe_cc_s]
        else:
            where.append(sql_text("citizenlab.cc = 'ZZ'"))

    if probe_cc_s:
        where.append(sql_text("probe_cc IN :probe_cc_s"))
        query_params["probe_cc_s"] = probe_cc_s

    if probe_asn_s:
        where.append(sql_text("probe_asn IN :probe_asn_s"))
        query_params["probe_asn_s"] = probe_asn_s

    if ooni_run_link_id_raw:
        ooni_run_link_id_s = commasplit(ooni_run_link_id_raw)
        where.append(sql_text("ooni_run_link_id IN :ooni_run_link_id_s"))
        query_params["ooni_run_link_id_s"] = ooni_run_link_id_s

    if since:
        where.append(sql_text("measurement_start_time >= :since"))
        query_params["since"] = since

    if until:
        where.append(sql_text("measurement_start_time < :until"))
        query_params["until"] = until

    if test_name_s:
        where.append(sql_text("test_name IN :test_name_s"))
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
            sql_table("citizenlab"),
            sql_text("citizenlab.url = fastpath.input"),
        )

    where_expr = and_(*where)
    query = select(cols).where(where_expr).select_from(table)  # type: ignore

    # Add group-by
    for g in group_by:
        query = query.group_by(g).order_by(g)

    try:
        if dimension_cnt > 0:
            r: Any = list(query_click(db, query, query_params, query_prio=4))
        else:
            r = query_click_one_row(db, query, query_params, query_prio=4)

        pq = db.last_query
        assert pq
        msg = f"Stats: {pq.progress.rows} {pq.progress.bytes} {pq.progress.total_rows} {pq.elapsed}"
        log.info(msg)

        if cacheable:
            response.headers["Cache-Control"] = f"max_age={3600 * 24}"

        headers = {}
        if resp_format == "CSV":
            csv_data = convert_to_csv(r)
            if download:
                headers[
                    "Content-Disposition"
                ] = f"attachment; filename=ooni-aggregate-data.csv"

            return Response(content=csv_data, media_type="text/csv", headers=headers)

        else:
            if download:
                headers[
                    "Content-Disposition"
                ] = f"attachment; filename=ooni-aggregate-data.csv"
                set_dload(response, "ooni-aggregate-data.json")
            return MeasurementAggregation(
                v=0,
                dimension_count=dimension_cnt,
                db_stats=DBStats(
                    row_count=pq.progress.rows,
                    bytes=pq.progress.bytes,
                    total_row_count=pq.progress.total_rows,
                    elapsed_seconds=pq.elapsed,
                ),
                result=r,
            )

    except Exception as e:
        return jerror(str(e), v=0)
