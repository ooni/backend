import time
import math
from datetime import datetime
from typing import List, Literal, Optional, Tuple, Union, Dict
from typing_extensions import Annotated
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from .utils import get_measurement_start_day_agg, TimeGrains, parse_probe_asn_to_int
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
    dns_isp_blocked: Optional[float]
    dns_isp_down: Optional[float]
    dns_isp_ok: Optional[float]
    dns_other_blocked: Optional[float]
    dns_other_down: Optional[float]
    dns_other_ok: Optional[float]

    tcp_blocked: Optional[float]
    tcp_down: Optional[float]
    tcp_ok: Optional[float]

    tls_blocked: Optional[float]
    tls_down: Optional[float]
    tls_ok: Optional[float]

    likely_blocked_protocols: List[Tuple[str, float]]
    blocked_max_outcome: Optional[str]
    blocked_max: Optional[float]

    dns_isp_blocked_outcome: Optional[str]
    dns_other_blocked_outcome: Optional[str]
    tcp_blocked_outcome: Optional[str]
    tls_blocked_outcome: Optional[str]


class AggregationEntry(BaseModel):
    count: float

    measurement_start_day: Optional[datetime] = None

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


# editable chart link: https://excalidraw.com/#json=mnoOrMXdSDLVirr8Albuu,xRyHC8-8JlsTTEovwNxOdQ
analysis_description = """
## Overview

The goal of analysis is to use observations to produce likelyhood of network
interference vectors.
These vectors are expressing the level of belief we have in a certain target
(eg. a web resource) being blocked (ie. intentionally unavailable), down (ie.
unavailable, but not due to a restriction) or ok (ie. available and not
blocked) in a certain location (eg. country, ASN pair) in a given window of time
(eg. from the 1st of January 2025 until the 20th of January 2025).

We express the outcome space a likelyhood vector where each value is between 0.0
and 1.0, where 1.0 is absolute certainty, while 0.0 is the opposite.

It's useful to represent the outcome space as the following Venn diagram:

![https://raw.githubusercontent.com/ooni/backend/a12522a729b6880b5e604cb80d6500e27d82fd57/ooniapi/services/oonimeasurements/docs/loni-outcome-space.svg]

Below we expand upon the meaning of each set:

* B = { something is blocked, and also down or ok or both or only blocked}
* D = { something is down, but also blocked or ok or both or only down}
* K = { something is ok, and also down or blocked or both or only ok}
* PB = { something is blocked, but is NOT down or blocked}
* PD = { something is down, but is NOT blocked or ok}
* PK = { something is ok, but is NOT down or blocked}
* BD¬K = { something is blocked and down, but NOT ok}
* BK¬D = { something is blocked and ok, but NOT down}
* DK¬B = { something is down and ok, but NOT blocked}
* BDK = { something is blocked and down and ok}

At first one might expect the intersection sets to always be null, after
something can't be blocked and ok at the same time, however it's important to
keep in mind that these likelyhood vectors apply to a variable location and time
contour. This means that within a certain window of time the target might be
unavailable only transiently or it might be unavailable only in a certain subset
of all locations, resulting in it being, for example, blocked and ok at the same
time.

While it would be nice to have something where the properties of these
likelyhood vectors are expressed in such a way where they are indepndent from
one another (ie. they sum to 1.0), doing so is not so easy.
For example, it's non-trivial to calculate the "Pure" (PB, PD, PK) values or the
¬ values.

As a result we decide to focus in this first iteration on just estimating B,
which we approximate by calculating a robust maximum value on the fuzzy logic
based analysis vectors.
Specifically they are estimated using quantiles over all the
measurement_analysis tables. We don't use just a simple maximum, a single
outlier would obviously skew the whole calculation.

We then proceed to estimate the likelyhood of the blocking happening at each
level, dns_isp (probe_asn == resolver_asn), dns_other (probe_asn !=
resolver_asn), tcp or tls.

We don't consider http level blocking, since that's prone to issues related to
older versions of the engine not properly marking the address of the
measurement.

Each entry inside of the analysis endpoint contains the following:

* dns_isp_blocked: value between 0-1 (equivalent to P(B))
* dns_isp_down: value between 0-1 (equivalent to P(D))
* dns_isp_ok: value between 0-1 (equivalent to P(K))

* dns_other_blocked: value between 0-1 (equivalent to P(B))
* dns_other_down: value between 0-1 (equivalent to P(D))
* dns_other_ok: value between 0-1 (equivalent to P(K))

* tcp_blocked: value between 0-1 (equivalent to P(B))
* tcp_down: value between 0-1 (equivalent to P(D))
* tcp_ok: value between 0-1 (equivalent to P(K))

* tls_blocked: value between 0-1 (equivalent to P(B))
* tls_down: value between 0-1 (equivalent to P(D))
* tls_ok: value between 0-1 (equivalent to P(K))

* likely_blocked_protocols: is a list of strings identifying the protocols and
  failure reason string with the associated max blocked likelyhood. (eg.
  [(tcp.generic_timeout_error, 0.75)]). They are sorted by blocked likelyhood
* blocked_max_outcome: the string of the first item in the likely_blocked_protocols list (eg. tcp.generic_timeout_error)
* blocked_max: value between 0-1 of the first item in the likely_blocked_protocols list (eg. 0.75)

* dns_isp_blocked_outcome: string value of the reason for which dns_isp is likely blocked
* dns_other_blocked_outcome: string value of the reason for which dns_other is likely blocked
* tcp_blocked_outcome: string value of the reason for which tcp is likely blocked
* tls_blocked_outcome: string value of the reason for which tls is likely blocked

It's important to remember that since B, D and K are not independent, P(K) +
P(D) + P(B) does not = 1!

"""


def format_aggregate_query(extra_cols: Dict[str, str], where: str):
    return f"""
    SELECT
    {",".join(extra_cols.keys())},
    probe_analysis,
    count,

    dns_isp_blocked_q99 as dns_isp_blocked,
    dns_isp_down_q99 as dns_isp_down,
    dns_isp_ok_q99 as dns_isp_ok,

    dns_other_blocked_q99 as dns_other_blocked,
    dns_other_down_q99 as dns_other_down,
    dns_other_ok_q99 as dns_other_ok,

    tcp_blocked_q99 as tcp_blocked,
    tcp_down_q99 as tcp_down,
    tcp_ok_q99 as tcp_ok,

    tls_blocked_q99 as tls_blocked,
    tls_down_q99 as tls_down,
    tls_ok_q99 as tls_ok,

    arrayFirst(x -> TRUE, top_dns_isp_failures_by_impact).1 as dns_isp_blocked_outcome,

    arrayFirst(x -> TRUE, top_dns_other_failures_by_impact).1 as dns_other_blocked_outcome,

    arrayFirst(x -> TRUE, top_tcp_failures_by_impact).1 as tcp_blocked_outcome,

    arrayFirst(x -> TRUE, top_tls_failures_by_impact).1 as tls_blocked_outcome,

    arrayMap(
        x -> multiIf(
            x.2 = 'dns_isp',
            (CONCAT(x.2, '.', dns_isp_blocked_outcome), dns_isp_blocked),
            x.2 = 'dns_other',
            (CONCAT(x.2, '.', dns_other_blocked_outcome), dns_other_blocked),
            x.2 = 'tcp',
            (CONCAT(x.2, '.', tcp_blocked_outcome), tcp_blocked),
            x.2 = 'tls',
            (CONCAT(x.2, '.', tls_blocked_outcome), tls_blocked),
            ('none', 0.0)
        ),
        arraySort(
            x -> -x.1,
            arrayFilter(
                x -> x.1 > 0.5,
                [
                    (dns_isp_blocked, 'dns_isp'),
                    (dns_other_blocked, 'dns_other'),
                    (tcp_blocked, 'tcp'),
                    (tls_blocked, 'tls')
                ]
            )
        )
    ) as likely_blocked_protocols,

    IF(
        likely_blocked_protocols IS NOT NULL AND length(likely_blocked_protocols) > 0,
        arrayElement(likely_blocked_protocols, 1),
        NULL
    ) as blocked_max_protocol

    FROM (
        WITH
        IF(resolver_asn = probe_asn, 1, 0) as is_isp_resolver,
        multiIf(
            top_dns_failure IN ('android_dns_cache_no_data', 'dns_nxdomain_error'),
            'nxdomain',
            coalesce(top_dns_failure , 'got_answer')
        ) as dns_failure

        SELECT
            {",".join(extra_cols.values())},
            COUNT() as count,

            anyHeavy(top_probe_analysis) as probe_analysis,

            topKWeightedIf(10, 3, 'counts')(
                dns_failure,
                toInt8(dns_blocked * 100),
                is_isp_resolver = 1
            ) as top_dns_isp_failures_by_impact,

            topKWeightedIf(10, 3, 'counts')(
                dns_failure,
                toInt8(dns_blocked * 100),
                is_isp_resolver = 0
            ) as top_dns_other_failures_by_impact,

            topKWeighted(10, 3, 'counts')(
                top_tcp_failure,
                toInt8(tcp_blocked * 100)
            ) as top_tcp_failures_by_impact,

            topKWeighted(10, 3, 'counts')(
                top_tls_failure,
                toInt8(tls_blocked * 100)
            ) as top_tls_failures_by_impact,

            quantileIf(0.95)(dns_blocked, is_isp_resolver = 1) as dns_isp_blocked_q99,
            quantileIf(0.95)(dns_down, is_isp_resolver = 1) as dns_isp_down_q99,
            quantileIf(0.95)(dns_ok, is_isp_resolver = 1) as dns_isp_ok_q99,

            quantileIf(0.95)(dns_blocked, is_isp_resolver = 0) as dns_other_blocked_q99,
            quantileIf(0.95)(dns_down, is_isp_resolver = 0) as dns_other_down_q99,
            quantileIf(0.95)(dns_ok, is_isp_resolver = 0) as dns_other_ok_q99,

            quantile(0.95)(tcp_blocked) as tcp_blocked_q99,
            quantile(0.95)(tcp_down) as tcp_down_q99,
            quantile(0.95)(tcp_ok) as tcp_ok_q99,

            quantile(0.95)(tls_blocked) as tls_blocked_q99,
            quantile(0.95)(tls_down) as tls_down_q99,
            quantile(0.95)(tls_ok) as tls_ok_q99

        FROM analysis_web_measurement

        {where}
        GROUP BY {", ".join(extra_cols.keys())}
        ORDER BY {", ".join(extra_cols.keys())}
    )
    """


@router.get(
    "/v1/aggregation/analysis",
    tags=["aggregation", "analysis"],
    description=analysis_description,
)
@parse_probe_asn_to_int
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
        "dns_isp_blocked_outcome",
        "dns_other_blocked_outcome",
        "tcp_blocked_outcome",
        "tls_blocked_outcome",
        "likely_blocked_protocols",
        "blocked_max_protocol",
    ]

    results: List[AggregationEntry] = []
    if rows and isinstance(rows, list):
        for row in rows:
            d = dict(zip(list(extra_cols.keys()) + fixed_cols, row))
            blocked_max_protocol = d["blocked_max_protocol"]

            def nan_to_none(val):
                if math.isnan(val):
                    return None
                return val

            loni = Loni(
                dns_isp_blocked=nan_to_none(d["dns_isp_blocked"]),
                dns_isp_down=nan_to_none(d["dns_isp_down"]),
                dns_isp_ok=nan_to_none(d["dns_isp_ok"]),
                dns_other_blocked=nan_to_none(d["dns_other_blocked"]),
                dns_other_down=nan_to_none(d["dns_other_down"]),
                dns_other_ok=nan_to_none(d["dns_other_ok"]),
                tls_blocked=nan_to_none(d["tls_blocked"]),
                tls_down=nan_to_none(d["tls_down"]),
                tls_ok=nan_to_none(d["tls_ok"]),
                tcp_blocked=nan_to_none(d["tcp_blocked"]),
                tcp_down=nan_to_none(d["tcp_down"]),
                tcp_ok=nan_to_none(d["tcp_ok"]),
                likely_blocked_protocols=d["likely_blocked_protocols"],
                blocked_max_outcome=(
                    blocked_max_protocol[0] if blocked_max_protocol else ""
                ),
                blocked_max=(
                    nan_to_none(blocked_max_protocol[1])
                    if blocked_max_protocol
                    else 0.0
                ),
                dns_isp_blocked_outcome=d["dns_isp_blocked_outcome"],
                dns_other_blocked_outcome=d["dns_other_blocked_outcome"],
                tcp_blocked_outcome=d["tcp_blocked_outcome"],
                tls_blocked_outcome=d["tls_blocked_outcome"],
            )

            entry = AggregationEntry(
                count=d["count"],
                measurement_start_day=d.get("measurement_start_day"),
                loni=loni,
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
