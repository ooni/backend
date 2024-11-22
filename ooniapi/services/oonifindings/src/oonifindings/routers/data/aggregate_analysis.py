from datetime import date, datetime, timedelta, timezone
from time import time
from typing import List, Literal, Optional, Union, Dict
from typing_extensions import Annotated
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from .utils import get_measurement_start_day_agg, TimeGrains
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
    "measurement_start_day",
    "domain",
    "probe_cc",
    "probe_asn",
    "test_name",
]


class DBStats(BaseModel):
    bytes: int
    elapsed_seconds: float
    row_count: int
    total_row_count: int


class AggregationEntry(BaseModel):
    anomaly_count: float
    confirmed_count: float
    failure_count: float
    ok_count: float
    measurement_count: float

    measurement_start_day: date
    outcome_label: str
    outcome_value: float

    domain: Optional[str] = None
    probe_cc: Optional[str] = None
    probe_asn: Optional[int] = None


class AggregationResponse(BaseModel):
    # TODO(arturo): these keys are inconsistent with the other APIs
    db_stats: DBStats
    dimension_count: int
    result: List[AggregationEntry]


@router.get("/v1/aggregation/analysis", tags=["aggregation", "analysis"])
async def get_aggregation_analysis(
    axis_x: Annotated[AggregationKeys, Query()] = "measurement_start_day",
    axis_y: Annotated[Optional[AggregationKeys], Query()] = None,
    category_code: Annotated[Optional[str], Query()] = None,
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
        if isinstance(probe_asn, str) and probe_asn.startswith("AS"):
            probe_asn = int(probe_asn[2:])
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
    # if category_code is not None:
    #     q_args["category_code"] = category_code
    #     and_clauses.append("%(category_code)s")
    #     extra_cols["category_code"] = "category_code"
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

    q = f"""
    WITH
    mapFilter((k, v) -> v != 0, dns_nok_outcomes) as dns_outcomes,
    mapFilter((k, v) -> v != 0, tcp_nok_outcomes) as tcp_outcomes,
    mapFilter((k, v) -> v != 0, tls_nok_outcomes) as tls_outcomes,

    arrayZip(mapKeys(dns_outcomes), mapValues(dns_outcomes)) as dns_outcome_list,
    arraySum((v) -> v.2, dns_outcome_list) as dns_nok_sum,
    arraySort((v) -> -v.2, arrayMap((v) -> (v.1, v.2/dns_nok_sum), dns_outcome_list)) as dns_outcomes_norm,

    arrayZip(mapKeys(tcp_outcomes), mapValues(tcp_outcomes)) as tcp_outcome_list,
    arraySum((v) -> v.2, tcp_outcome_list) as tcp_nok_sum,
    arraySort((v) -> -v.2, arrayMap((v) -> (v.1, v.2/tcp_nok_sum), tcp_outcome_list)) as tcp_outcomes_norm,

    arrayZip(mapKeys(tls_outcomes), mapValues(tls_outcomes)) as tls_outcome_list,
    arraySum((v) -> v.2, tls_outcome_list) as tls_nok_sum,
    arraySort((v) -> -v.2, arrayMap((v) -> (v.1, v.2/tls_nok_sum), tls_outcome_list)) as tls_outcomes_norm,

    arraySort(
        (v) -> -v.2,
        [
            (dns_outcome_nok_label, dns_outcome_nok_value),
            (tcp_outcome_nok_label, tcp_outcome_nok_value),
            (tls_outcome_nok_label, tls_outcome_nok_value),
            IF(
                tls_ok_sum = 0 AND tls_outcome_nok_value = 0,
                -- Special case for when the tested target was not supporting HTTPS and hence the TLS outcome is not so relevant
                ('ok', arrayMin([dns_outcome_ok_value, tcp_outcome_ok_value])),
                ('ok', arrayMin([dns_outcome_ok_value, tcp_outcome_ok_value, tls_outcome_ok_value]))
            )
        ]
    ) as all_outcomes_sorted,

    arrayConcat(dns_outcomes_norm, tcp_outcomes_norm, tls_outcomes_norm) as all_nok_outcomes,

    dns_outcomes_norm[1].1 as dns_outcome_nok_label,
    dns_outcomes_norm[1].2 as dns_outcome_nok_value,

    tcp_outcomes_norm[1].1 as tcp_outcome_nok_label,
    tcp_outcomes_norm[1].2 as tcp_outcome_nok_value,

    tls_outcomes_norm[1].1 as tls_outcome_nok_label,
    tls_outcomes_norm[1].2 as tls_outcome_nok_value,

    IF(dns_ok_sum > 0, 1 - dns_outcome_nok_value, 0) as dns_outcome_ok_value,
    IF(tcp_ok_sum > 0, 1 - tcp_outcome_nok_value, 0) as tcp_outcome_ok_value,
    IF(tls_ok_sum > 0, 1 - tls_outcome_nok_value, 0) as tls_outcome_ok_value,

    all_outcomes_sorted[1].1 as final_outcome_label,
    IF(final_outcome_label = 'ok', all_outcomes_sorted[1].2, all_outcomes_sorted[1].2) as final_outcome_value

    SELECT

    {",".join(extra_cols.keys())},
    probe_analysis,
    all_nok_outcomes as all_outcomes,
    final_outcome_label as outcome_label,
    final_outcome_value as outcome_value

    FROM (
        WITH
        IF(resolver_asn = probe_asn, 1, 0) as is_isp_resolver,
        multiIf(
            top_dns_failure IN ('android_dns_cache_no_data', 'dns_nxdomain_error'),
            'nxdomain',
            coalesce(top_dns_failure, 'got_answer')
        ) as dns_failure
        SELECT
            {",".join(extra_cols.values())},

            anyHeavy(top_probe_analysis) as probe_analysis,

            sumMap(
                map(
                    CONCAT(IF(is_isp_resolver, 'dns_isp.blocked.', 'dns_other.blocked.'), dns_failure), dns_blocked_max,
                    CONCAT(IF(is_isp_resolver, 'dns_isp.down.', 'dns_other.down.'), dns_failure), dns_down_max
                )
            ) as dns_nok_outcomes,
            sum(dns_ok_max) as dns_ok_sum,

            sumMap(
                map(
                    CONCAT('tcp.blocked.', coalesce(top_tcp_failure, '')), tcp_blocked_max,
                    CONCAT('tcp.down.', coalesce(top_tcp_failure, '')), tcp_down_max
                )
            )  as tcp_nok_outcomes,
            sum(tcp_ok_max) as tcp_ok_sum,

            sumMap(
                map(
                    CONCAT('tls.blocked.', coalesce(top_tls_failure, '')), tls_blocked_max,
                    CONCAT('tls.down.', coalesce(top_tls_failure, '')), tls_down_max
                )
            ) as tls_nok_outcomes,
            sum(tls_ok_max) as tls_ok_sum

        FROM ooni.analysis_web_measurement
        {where}
        GROUP BY {", ".join(extra_cols.keys())}
        ORDER BY {", ".join(extra_cols.keys())}
    )
    """

    t = time.perf_counter()
    log.info(f"running query {q} with {q_args}")
    rows = db.execute(q, q_args)

    fixed_cols = ["probe_analysis", "all_outcomes", "outcome_label", "outcome_value"]

    results: List[AggregationEntry] = []
    if rows and isinstance(rows, list):
        for row in rows:
            print(row)
            d = dict(zip(list(extra_cols.keys()) + fixed_cols, row))
            outcome_value = d["outcome_value"]
            outcome_label = d["outcome_label"]
            anomaly_count = 0
            confirmed_count = 0
            failure_count = 0
            ok_count = 0
            if outcome_label == "ok":
                ok_count = outcome_value
            elif "blocked." in outcome_label:
                if outcome_value >= anomaly_sensitivity:
                    confirmed_count = outcome_value
                else:
                    anomaly_count = outcome_value

            # Map "down" to failures
            else:
                failure_count = outcome_value

            entry = AggregationEntry(
                anomaly_count=anomaly_count,
                confirmed_count=confirmed_count,
                failure_count=failure_count,
                ok_count=ok_count,
                measurement_count=1.0,
                measurement_start_day=d["measurement_start_day"],
                outcome_label=outcome_label,
                outcome_value=outcome_value,
                domain=d.get("domain"),
                probe_cc=d.get("probe_cc"),
                probe_asn=d.get("probe_asn"),
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
        result=results,
    )
