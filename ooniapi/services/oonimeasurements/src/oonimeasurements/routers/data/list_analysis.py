from datetime import datetime
import logging
import math
import time
from typing import List, Literal, Optional, Union
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing_extensions import Annotated

from ...common.dependencies import get_settings
from ...dependencies import get_clickhouse_session
from .utils import SinceUntil, parse_probe_asn_to_int, test_name_to_group, utc_30_days_ago, utc_today

log = logging.getLogger(__name__)

from fastapi import APIRouter

router = APIRouter()


class ResponseMetadata(BaseModel):
    count: int
    current_page: int
    limit: int
    next_url: str
    offset: int
    pages: int
    query_time: float


class AnalysisEntry(BaseModel):
    measurement_uid: str
    measurement_start_time: datetime
    network_type: str
    probe_asn: int
    probe_cc: str
    probe_as_org_name: str
    resolver_asn: int
    resolver_as_cc: str
    domain: str
    input: str
    test_name: str
    top_probe_analysis: Optional[str]
    top_dns_failure: Optional[str]
    top_tcp_failure: Optional[str]
    top_tls_failure: Optional[str]
    dns_blocked: float
    dns_down: float
    dns_ok: float
    tcp_blocked: float
    tcp_down: float
    tcp_ok: float
    tls_blocked: float
    tls_down: float
    tls_ok: float


class ListAnalysisResponse(BaseModel):
    metadata: ResponseMetadata
    results: List[AnalysisEntry]


@router.get("/v1/analysis", tags=["analysis", "list_data"])
@parse_probe_asn_to_int
async def list_measurements(
    measurement_uid: Annotated[Optional[str], Query()] = None,
    probe_asn: Annotated[Union[int, str, None], Query()] = None,
    probe_cc: Annotated[Optional[str], Query(max_length=2, min_length=2)] = None,
    test_name: Annotated[Optional[str], Query()] = None,
    since: SinceUntil = utc_30_days_ago(),
    until: SinceUntil = utc_today(),
    order_by: Annotated[
        Literal[
            "measurement_start_time",
            "input",
            "probe_cc",
            "probe_asn",
            "test_name",
        ],
        Query(),
    ] = "measurement_start_time",
    order: Annotated[Optional[Literal["asc", "desc", "ASC", "DESC"]], Query()] = "DESC",
    offset: Annotated[int, Query()] = 0,
    limit: Annotated[int, Query()] = 100,
    ooni_run_link_id: Annotated[Optional[str], Query()] = None,
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings),
) -> ListAnalysisResponse:
    q_args = {}
    and_clauses = []
    if measurement_uid is not None:
        q_args["measurement_uid"] = measurement_uid
        and_clauses.append("measurement_uid = %(measurement_uid)s")
    if probe_asn is not None:
        q_args["probe_asn"] = probe_asn
        and_clauses.append("probe_asn = %(probe_asn)d")
    if probe_cc is not None:
        q_args["probe_cc"] = probe_cc
        and_clauses.append("probe_cc = %(probe_cc)s")
    if test_name is not None:
        q_args["test_name"] = test_name
        and_clauses.append("test_name = %(test_name)s")
    if ooni_run_link_id is not None:
        q_args["ooni_run_link_id"] = ooni_run_link_id
        and_clauses.append("ooni_run_link_id = %(ooni_run_link_id)s")

    if since is not None:
        q_args["since"] = since
        and_clauses.append("measurement_start_time >= %(since)s")
    if until is not None:
        and_clauses.append("measurement_start_time <= %(until)s")
        q_args["until"] = until

    cols = list(AnalysisEntry.model_json_schema()["properties"].keys())
    q = f"SELECT {','.join(cols)} FROM analysis_web_measurement"
    if len(and_clauses) > 0:
        q += " WHERE "
        q += " AND ".join(and_clauses)
    q += f" ORDER BY {order_by} {order} LIMIT {limit} OFFSET {offset}"

    t = time.perf_counter()
    log.info(f"running query {q} with {q_args}")
    rows = db.execute(q, q_args)

    results: List[AnalysisEntry] = []
    if rows and isinstance(rows, list):
        for row in rows:
            d = dict(zip(cols, row))
            results.append(AnalysisEntry(**d))

    response = ListAnalysisResponse(
        metadata=ResponseMetadata(
            count=-1,
            current_page=math.ceil(offset / limit) + 1,
            limit=limit,
            next_url=f"{settings.base_url}/api/v1/analysis?offset=100&limit=100",
            offset=offset,
            pages=-1,
            query_time=time.perf_counter() - t,
        ),
        results=results,
    )

    return response
