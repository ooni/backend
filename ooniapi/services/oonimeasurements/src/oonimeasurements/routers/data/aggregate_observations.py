from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Literal, Optional, Union, Dict
from typing_extensions import Annotated
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel


from ...dependencies import get_clickhouse_session
from .utils import (
    SinceUntil,
    get_measurement_start_day_agg,
    TimeGrains,
    utc_30_days_ago,
    utc_today,
)

from fastapi import APIRouter

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
    ip: Annotated[List[str] | None, Query()] = None,
    ooni_run_link_id: Annotated[Optional[str], Query()] = None,
    since: SinceUntil = utc_30_days_ago(),
    until: SinceUntil = utc_today(),
    time_grain: Annotated[TimeGrains, Query()] = "day",
    db=Depends(get_clickhouse_session),
) -> AggregationResponse:
    timestamp_str = get_measurement_start_day_agg(time_grain)
    column_keys = ["observation_count"]
    columns = []
    and_list = []
    order_by = ["obs_count"]
    params_filter: Dict[str, Any] = {"since": since, "until": until}
    selected_columns = ""
    group_by_str = ""
    order_by_str = ""
    and_str = ""

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

    if "timestamp" in group_by:
        columns.append(f"{timestamp_str} as timestamp")
        column_keys.append("timestamp")
        order_by = ["timestamp"] + order_by

    if "failure" in group_by:
        columns.append(
            f"""multiIf(
dns_failure IS NOT NULL,
CONCAT('dns_', dns_failure),
tcp_failure IS NOT NULL,
CONCAT('tcp_', tcp_failure),
multiIf(
tls_handshake_last_operation = 'write_1',
CONCAT('tls_', tls_failure, '_after_CH'),
tls_failure IS NULL AND tls_server_name IS NOT NULL,
'none',
CONCAT('tls_', tls_failure)
)
) as failure
"""
        )
        column_keys.append("failure")
        and_list.append(
            # We exclude observations where we only have the HTTP/HTTPS observations
            """(dns_failure IS NOT NULL
OR tcp_failure IS NOT NULL
OR tls_failure IS NOT NULL
OR tls_server_name IS NOT NULL
)
"""
        )

    for column in group_by:
        if column not in column_keys:
            columns.append(column)
            column_keys.append(column)

    selected_columns = ",".join(columns)
    if len(and_list) > 0:
        and_str = "AND " + "AND ".join(and_list)

    group_by_str = "GROUP BY " + ",".join(group_by)

    query = f"""
    SELECT
COUNT() as obs_count,
{selected_columns}
FROM obs_web
WHERE measurement_start_time > %(since)s
AND measurement_start_time < %(until)s
{and_str}
{group_by_str}
{order_by_str}
"""
    entries = []
    for row in db.execute_iter(query, params_filter):
        d = dict(zip(column_keys, row))
        entries.append(AggregationEntry(**d))
    return AggregationResponse(results=entries)
