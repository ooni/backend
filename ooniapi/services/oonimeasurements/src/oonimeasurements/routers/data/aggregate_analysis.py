import time
from datetime import date, datetime, timedelta, timezone
from typing import List, Literal, Optional, Union, Dict
from typing_extensions import Annotated
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from .utils import get_measurement_start_day_agg, TimeGrains, parse_probe_asn
from ...sql import format_aggregate_query
from ...dependencies import (
    get_clickhouse_session,
)
from .list_analysis import (
    SinceUntil,
    utc_30_days_ago,
    utc_today,
)

import logging

from fastapi import APIRouter

router = APIRouter()

log = logging.getLogger(__name__)


AggregationKeys = Literal[
    "measurement_start_day", "domain", "probe_cc", "probe_asn", "test_name", "input"
]


class DBStats(BaseModel):
    bytes: int
    elapsed_seconds: float
    row_count: int
    total_row_count: int


class Loni(BaseModel):
    dns_isp_blocked: float
    dns_isp_down: float
    dns_isp_ok: float
    dns_other_blocked: float
    dns_other_down: float
    dns_other_ok: float
    tls_blocked: float
    tls_down: float
    tls_ok: float
    tcp_blocked: float
    tcp_down: float
    tcp_ok: float

    dns_isp_outcome: str
    dns_other_outcome: str
    tcp_outcome: str
    tls_outcome: str


class AggregationEntry(BaseModel):
    count: float

    measurement_start_day: Optional[datetime] = None

    outcome_label: str
    outcome_ok: float
    outcome_blocked: float
    outcome_down: float

    loni: Loni

    domain: Optional[str] = None
    probe_cc: Optional[str] = None
    probe_asn: Optional[int] = None
    test_name: Optional[str] = None
    input: Optional[str] = None


class AggregationResponse(BaseModel):
    # TODO(arturo): these keys are inconsistent with the other APIs
    db_stats: DBStats
    dimension_count: int
    results: List[AggregationEntry]


@router.get("/v1/aggregation/analysis", tags=["aggregation", "analysis"])
async def get_aggregation_analysis(
    axis_x: Annotated[AggregationKeys, Query()] = "measurement_start_day",
    axis_y: Annotated[Optional[AggregationKeys], Query()] = None,
    test_name: Annotated[Optional[str], Query()] = None,
    domain: Annotated[Optional[str], Query()] = None,
    input: Annotated[Optional[str], Query()] = None,
    probe_asn: Annotated[Union[int, str, None], Query()] = None,
    probe_cc: Annotated[Optional[str], Query(min_length=2, max_length=2)] = None,
    ooni_run_link_id: Annotated[Optional[str], Query()] = None,
    since: SinceUntil = utc_30_days_ago(),
    until: SinceUntil = utc_today(),
    time_grain: Annotated[TimeGrains, Query()] = "day",
    anomaly_sensitivity: Annotated[float, Query()] = 0.9,
    format: Annotated[Literal["JSON", "CSV"], Query()] = "JSON",
    download: Annotated[bool, Query()] = False,
    db=Depends(get_clickhouse_session),
) -> AggregationResponse:
    q_args = {}
    and_clauses = []
    extra_cols = {}
    dimension_count = 1
    if axis_x == "measurement_start_day":
        # TODO(arturo): wouldn't it be nicer if we dropped the time_grain
        # argument and instead used axis_x IN (measurement_start_day,
        # measurement_start_hour, ..)?
        extra_cols["measurement_start_day"] = (
            f"{get_measurement_start_day_agg(time_grain)} as measurement_start_day"
        )
    elif axis_x:
        extra_cols[axis_x] = axis_x

    if probe_asn is not None:
        probe_asn = parse_probe_asn(probe_asn)
        q_args["probe_asn"] = probe_asn
        and_clauses.append("probe_asn = %(probe_asn)d")
        extra_cols["probe_asn"] = "probe_asn"
    if probe_cc is not None:
        q_args["probe_cc"] = probe_cc
        and_clauses.append("probe_cc = %(probe_cc)s")
        extra_cols["probe_cc"] = "probe_cc"
    if test_name is not None:
        q_args["test_name"] = test_name
        and_clauses.append("test_name = %(test_name)s")
        extra_cols["test_name"] = "test_name"
    if ooni_run_link_id is not None:
        q_args["ooni_run_link_id"] = ooni_run_link_id
        and_clauses.append("%(ooni_run_link_id)s")
        extra_cols["ooni_run_link_id"] = "ooni_run_link_id"
    if domain is not None:
        q_args["domain"] = domain
        and_clauses.append("domain = %(domain)s")
        extra_cols["domain"] = "domain"
    if input is not None:
        q_args["input"] = input
        and_clauses.append("input = %(input)s")
        extra_cols["input"] = "input"

    if axis_y:
        dimension_count += 1
        if axis_y == "measurement_start_day":
            # TODO(arturo): wouldn't it be nicer if we dropped the time_grain
            # argument and instead used axis_x IN (measurement_start_day,
            # measurement_start_hour, ..)?
            extra_cols["measurement_start_day"] = (
                f"{get_measurement_start_day_agg(time_grain)} as measurement_start_day"
            )
        else:
            extra_cols[axis_y] = axis_y

    if since is not None:
        q_args["since"] = since
        and_clauses.append("measurement_start_time >= %(since)s")
    if until is not None:
        and_clauses.append("measurement_start_time <= %(until)s")
        q_args["until"] = until

    where = ""
    if len(and_clauses) > 0:
        where += " WHERE "
        where += " AND ".join(and_clauses)

    q = format_aggregate_query(extra_cols, where)

    t = time.perf_counter()
    log.info(f"running query {q} with {q_args}")
    rows = db.execute(q, q_args)

    fixed_cols = [
        "probe_analysis",
        "count",
        "dns_isp_blocked",
        "dns_isp_down",
        "dns_isp_ok",
        "dns_other_blocked",
        "dns_other_down",
        "dns_other_ok",
        "tls_blocked",
        "tls_down",
        "tls_ok",
        "tcp_blocked",
        "tcp_down",
        "tcp_ok",
        "dns_isp_outcome",
        "dns_other_outcome",
        "tcp_outcome",
        "tls_outcome",
        "most_likely_ok",
        "most_likely_down",
        "most_likely_blocked",
        "most_likely_label",
    ]

    results: List[AggregationEntry] = []
    if rows and isinstance(rows, list):
        for row in rows:
            d = dict(zip(list(extra_cols.keys()) + fixed_cols, row))
            loni = Loni(
                dns_isp_blocked=d.get("dns_isp_blocked", 0.0),
                dns_isp_down=d.get("dns_isp_down", 0.0),
                dns_isp_ok=d.get("dns_isp_ok", 0.0),
                dns_other_blocked=d.get("dns_other_blocked", 0.0),
                dns_other_down=d.get("dns_other_down", 0.0),
                dns_other_ok=d.get("dns_other_ok", 0.0),
                tls_blocked=d.get("tls_blocked", 0.0),
                tls_down=d.get("tls_down", 0.0),
                tls_ok=d.get("tls_ok", 0.0),
                tcp_blocked=d.get("tcp_blocked", 0.0),
                tcp_down=d.get("tcp_down", 0.0),
                tcp_ok=d.get("tcp_ok", 0.0),
                dns_isp_outcome=d.get("dns_isp_outcome", ""),
                dns_other_outcome=d.get("dns_other_outcome", ""),
                tcp_outcome=d.get("tcp_outcome", ""),
                tls_outcome=d.get("tls_outcome", ""),
            )
            outcome_label = d["most_likely_label"]
            outcome_blocked = d["most_likely_blocked"]
            outcome_down = d["most_likely_down"]
            outcome_ok = d["most_likely_ok"]

            entry = AggregationEntry(
                count=d["count"],
                measurement_start_day=d.get("measurement_start_day"),
                loni=loni,
                outcome_label=outcome_label,
                outcome_blocked=outcome_blocked,
                outcome_down=outcome_down,
                outcome_ok=outcome_ok,
                domain=d.get("domain"),
                probe_cc=d.get("probe_cc"),
                probe_asn=d.get("probe_asn"),
                test_name=d.get("test_name"),
                input=d.get("input"),
            )
            results.append(entry)
    return AggregationResponse(
        db_stats=DBStats(
            bytes=-1,
            elapsed_seconds=time.perf_counter() - t,
            row_count=len(results),
            total_row_count=len(results),
        ),
        dimension_count=dimension_count,
        results=results,
    )
