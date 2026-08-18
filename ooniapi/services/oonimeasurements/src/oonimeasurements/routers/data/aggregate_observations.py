from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing_extensions import Annotated

from ...common.clickhouse_utils import async_query_click
from ...common.dependencies import get_clickhouse_session
from .utils import (
    SinceUntil,
    TimeGrains,
    get_measurement_start_day_agg,
    utc_30_days_ago,
    utc_today,
)

router = APIRouter()

import logging

log = logging.getLogger(__name__)


class AggregationEntry(BaseModel):
    observation_count: int
    failure: Optional[str] = None
    ip: Optional[str] = None

    hostname: Optional[str] = None
    probe_cc: Optional[str] = None
    probe_asn: Optional[int] = None
    test_name: Optional[str] = None
    measurement_uid: Optional[str] = None
    timestamp: Optional[datetime] = None


class AggregationResponse(BaseModel):
    results: List[AggregationEntry]


AggregationKeys = Literal[
    "timestamp",
    "failure",
    "hostname",
    "ip",
    "probe_cc",
    "probe_asn",
    "test_name",
    "measurement_uid",
]


@router.get(
    "/v1/aggregation/observations",
    response_model_exclude_none=True,
    tags=["aggregation", "observations"],
)
async def get_aggregation_observations(
    group_by: Annotated[List[AggregationKeys], Query()] = [
        "failure",
    ],
    test_name: Annotated[List[str] | None, Query()] = None,
    hostname: Annotated[List[str] | None, Query()] = None,
    probe_asn: Annotated[List[int] | None, Query()] = None,
    probe_cc: Annotated[List[str] | None, Query()] = None,
    resolver_asn: Annotated[List[str] | None, Query()] = None,
    ip: Annotated[List[str] | None, Query()] = None,
    measurement_uid: Annotated[List[str] | None, Query()] = None,
    ooni_run_link_id: Annotated[Optional[str], Query()] = None,
    since: Optional[SinceUntil] = None,
    until: Optional[SinceUntil] = None,
    time_grain: Annotated[TimeGrains, Query()] = "day",
    db=Depends(get_clickhouse_session),
) -> AggregationResponse:
    if since is None and not measurement_uid:
        since = utc_30_days_ago()
    if until is None and not measurement_uid:
        until = utc_today()

    timestamp_str = get_measurement_start_day_agg(time_grain)
    column_keys = ["observation_count"]
    columns = []
    and_list = []
    order_by = ["observation_count"]
    params_filter: Dict[str, Any] = {}
    selected_columns = ""
    group_by_str = ""
    order_by_str = ""
    where_str = ""

    if since is not None:
        and_list.append("measurement_start_time > %(since)s")
        params_filter["since"] = since
    if until is not None:
        and_list.append("measurement_start_time < %(until)s")
        params_filter["until"] = until

    if len(order_by) > 0:
        order_by_str = "ORDER BY " + ",".join(order_by) + " DESC"

    if probe_cc:
        and_list.append(f"probe_cc IN %(probe_cc)s")
        params_filter["probe_cc"] = probe_cc
        group_by.append("probe_cc")
        columns.append("probe_cc")
        column_keys.append("probe_cc")
    if probe_asn:
        and_list.append(f"probe_asn IN %(probe_asn)s")
        params_filter["probe_asn"] = probe_asn
        group_by.append("probe_asn")
        columns.append("probe_asn")
        column_keys.append("probe_asn")
    if resolver_asn:
        and_list.append(f"resolver_asn IN %(resolver_asn)s")
        params_filter["resolver_asn"] = probe_asn
        group_by.append("resolver_asn")
        columns.append("resolver_asn")
        column_keys.append("resolver_asn")
    if hostname:
        and_list.append(f"hostname IN %(hostname)s")
        params_filter["hostname"] = hostname
        group_by.append("hostname")
        columns.append("hostname")
        column_keys.append("hostname")
    if test_name:
        and_list.append(f"test_name IN %(test_name)s")
        params_filter["test_name"] = test_name
        group_by.append("test_name")
        columns.append("test_name")
        column_keys.append("test_name")
    if ip:
        and_list.append(f"ip IN %(ip)s")
        params_filter["ip"] = ip
        group_by.append("ip")
        columns.append("ip")
        column_keys.append("ip")
    if measurement_uid:
        and_list.append(f"measurement_uid IN %(measurement_uid)s")
        params_filter["measurement_uid"] = measurement_uid
        group_by.append("measurement_uid")
        columns.append("measurement_uid")
        column_keys.append("measurement_uid")

    if "timestamp" in group_by:
        columns.append(f"{timestamp_str} as timestamp")
        column_keys.append("timestamp")
        order_by = ["timestamp"] + order_by

    if "failure" in group_by:
        # We exclude observations that are only HTTP/HTTPS
        # since some older versions of the engine
        # don't allow us to properly connect them to the relevant address.
        # This means that if we were to present them here, we would be
        # double-counting some observations and for some we do not know if the failure
        # ocurred at TCP, TLS or HTTP levels.
        # We do this by filtering by observations that lead to a failure on dns
        # or have an IP value.
        and_list.append("(dns_failure IS NOT NULL OR ip IS NOT NULL)")

        # An important assumption about observations is made here.
        # This assumption is that if something fails at DNS, then it will fail
        # at TCP, which if it fails at TCP, it will fail at TLS and if it fails
        # at TLS it will fail at HTTP.
        # This assumption is in line with how web_connectivity currently works,
        # but may not be the case in the future.
        columns.append(
            f"""multiIf(
    dns_failure IS NOT NULL,
    IF(resolver_asn = probe_asn,
       CONCAT('dns_isp.', IF(startsWith(dns_failure, 'unknown_failure'), 'unknown_failure', dns_failure)),
       CONCAT('dns_other.', IF(startsWith(dns_failure, 'unknown_failure'), 'unknown_failure', dns_failure))
    ),
    tcp_failure IS NOT NULL,
    CONCAT('tcp.', IF(startsWith(tcp_failure, 'unknown_failure'), 'unknown_failure', tcp_failure)),
    tls_failure IS NOT NULL,
    CONCAT('tls.', IF(startsWith(tls_failure, 'unknown_failure'), 'unknown_failure', tls_failure)),
    http_failure IS NOT NULL,
    CONCAT(
        IF(startsWith(http_request_url, 'https://'), 'https.', 'http.'),
        IF(startsWith(http_failure, 'unknown_failure'), 'unknown_failure', http_failure)
    ),
    'none'
) as failure
"""
        )
        column_keys.append("failure")

    for column in group_by:
        if column not in column_keys:
            columns.append(column)
            column_keys.append(column)

    selected_columns = ",".join(columns)
    if len(and_list) > 0:
        where_str = "WHERE " + " AND ".join(and_list)

    group_by_str = "GROUP BY " + ",".join(group_by)

    query = f"""
    SELECT
COUNT() as observation_count,
{selected_columns}
FROM obs_web
{where_str}
{group_by_str}
{order_by_str}
"""
    entries = []
    res = await async_query_click(db, query, params_filter)
    for row in res:
        entries.append(AggregationEntry(**row))
    return AggregationResponse(results=entries)


CTRL_QUERY = (Path(__file__).parent / "ctrl_query.sql").read_text()

# ASNs of well known cloud / CDN providers, used to flag whether a control
# answer is likely to be behind shared infrastructure.
CLOUD_PROVIDER_ASNS = [
    13335,  # Cloudflare: https://www.peeringdb.com/net/4224
    209242,  # Cloudflare London, LLC
    20940,  # Akamai: https://www.peeringdb.com/net/2
    9002,  # Akamai RETN
    16625,  # Akamai Technologies, Inc.
    63949,  # Akamai Technologies, Inc.
    16509,  # Amazon.com, Inc.
    14618,  # Amazon.com, Inc.
    15169,  # Google LLC
    396982,  # Google Cloud: https://www.peeringdb.com/net/30878
    54113,  # Fastly, Inc
    8075,  # Microsoft Corporation
    8068,  # Microsoft Corporation
]


class CtrlGroundTruthEntry(BaseModel):
    hostname: str
    ip: str
    port: Optional[int] = None
    asn: Optional[int] = None
    as_org_name: Optional[str] = None
    is_cloud_provider: bool
    # was this IP ever returned as a DNS answer by the control
    in_dns_answers: bool
    # any TLS handshake against this IP succeeded in the control (across
    # every port it was tested on)
    tls_consistent: bool
    tcp_success_count: int
    tcp_failure_count: int
    tls_success_count: int
    tls_failure_count: int
    # same for every row of a given hostname (denormalized on purpose: this
    # is a flat table meant to be plotted/tabulated directly)
    dns_success_count: int
    dns_nxdomain_count: int
    dns_other_failure_count: int


class CtrlGroundTruthResponse(BaseModel):
    results: List[CtrlGroundTruthEntry]

@router.get(
    "/v1/aggregation/observations/ctrl_ground_truth",
    response_model_exclude_none=True,
    tags=["aggregation", "observations", "ctrl"],
)
async def get_ctrl_ground_truth(
    hostname: Annotated[List[str], Query()],
    since: Optional[SinceUntil] = None,
    until: Optional[SinceUntil] = None,
    db=Depends(get_clickhouse_session),
) -> CtrlGroundTruthResponse:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_time = since or now - timedelta(hours=1)
    end_time = until or now

    params = {
        "hostnames": hostname,
        "start_time": start_time,
        "end_time": end_time,
        "cloud_provider_asns": CLOUD_PROVIDER_ASNS,
    }
    res = await async_query_click(db, CTRL_QUERY, params)
    return CtrlGroundTruthResponse(
        results=[CtrlGroundTruthEntry(**row) for row in res]
    )
