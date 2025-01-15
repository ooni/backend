import dataclasses
import time
from datetime import date, datetime, timedelta
import math
from typing import List, Literal, Optional, Union
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing_extensions import Annotated

from ...common.dependencies import get_settings
from ...dependencies import get_clickhouse_session
from .utils import parse_probe_asn

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


class WebObservationEntry(BaseModel):
    measurement_uid: str
    input: Optional[str]
    report_id: str
    ooni_run_link_id: str

    measurement_start_time: datetime

    software_name: str
    software_version: str
    test_name: str
    test_version: str

    bucket_date: str

    probe_asn: int
    probe_cc: str

    probe_as_org_name: str
    probe_as_cc: str
    probe_as_name: str

    network_type: str
    platform: str
    origin: str
    engine_name: str
    engine_version: str
    architecture: str

    resolver_ip: str
    resolver_asn: int
    resolver_cc: str
    resolver_as_org_name: str
    resolver_as_cc: str

    observation_idx: int = 0
    created_at: Optional[datetime] = None

    target_id: Optional[str] = None
    hostname: Optional[str] = None

    transaction_id: Optional[int] = None

    ip: Optional[str] = None
    port: Optional[int] = None

    ip_asn: Optional[int] = None
    ip_as_org_name: Optional[str] = None
    ip_as_cc: Optional[str] = None
    ip_cc: Optional[str] = None
    ip_is_bogon: Optional[bool] = None

    # DNS related observation
    dns_query_type: Optional[str] = None
    dns_failure: Optional[str] = None
    dns_engine: Optional[str] = None
    dns_engine_resolver_address: Optional[str] = None

    dns_answer_type: Optional[str] = None
    dns_answer: Optional[str] = None
    # These should match those in the IP field, but are the annotations coming
    # from the probe
    dns_answer_asn: Optional[int] = None
    dns_answer_as_org_name: Optional[str] = None
    dns_t: Optional[float] = None

    # TCP related observation
    tcp_failure: Optional[str] = None
    tcp_success: Optional[bool] = None
    tcp_t: Optional[float] = None

    # TLS related observation
    tls_failure: Optional[str] = None

    tls_server_name: Optional[str] = None
    tls_outer_server_name: Optional[str] = None
    tls_echconfig: Optional[str] = None
    tls_version: Optional[str] = None
    tls_cipher_suite: Optional[str] = None
    tls_is_certificate_valid: Optional[bool] = None

    tls_end_entity_certificate_fingerprint: Optional[str] = None
    tls_end_entity_certificate_subject: Optional[str] = None
    tls_end_entity_certificate_subject_common_name: Optional[str] = None
    tls_end_entity_certificate_issuer: Optional[str] = None
    tls_end_entity_certificate_issuer_common_name: Optional[str] = None
    tls_end_entity_certificate_san_list: List[str] = dataclasses.field(
        default_factory=list
    )
    tls_end_entity_certificate_not_valid_after: Optional[datetime] = None
    tls_end_entity_certificate_not_valid_before: Optional[datetime] = None
    tls_certificate_chain_length: Optional[int] = None
    tls_certificate_chain_fingerprints: List[str] = dataclasses.field(
        default_factory=list
    )

    tls_handshake_read_count: Optional[int] = None
    tls_handshake_write_count: Optional[int] = None
    tls_handshake_read_bytes: Optional[float] = None
    tls_handshake_write_bytes: Optional[float] = None
    tls_handshake_last_operation: Optional[str] = None
    tls_handshake_time: Optional[float] = None
    tls_t: Optional[float] = None

    # HTTP related observation
    http_request_url: Optional[str] = None

    http_network: Optional[str] = None
    http_alpn: Optional[str] = None

    http_failure: Optional[str] = None

    http_request_body_length: Optional[int] = None
    http_request_method: Optional[str] = None

    http_runtime: Optional[float] = None

    http_response_body_length: Optional[int] = None
    http_response_body_is_truncated: Optional[bool] = None
    http_response_body_sha1: Optional[str] = None

    http_response_status_code: Optional[int] = None
    http_response_header_location: Optional[str] = None
    http_response_header_server: Optional[str] = None
    http_request_redirect_from: Optional[str] = None
    http_request_body_is_truncated: Optional[bool] = None
    http_t: Optional[float] = None

    probe_analysis: Optional[str] = None


ObservationEntry = Union[WebObservationEntry, BaseModel]


class ListObservationsResponse(BaseModel):
    metadata: ResponseMetadata
    results: List[ObservationEntry]


@router.get("/v1/observations", tags=["observations", "list_data"])
async def list_observations(
    report_id: Annotated[Optional[str], Query()] = None,
    probe_asn: Annotated[Union[int, str, None], Query()] = None,
    probe_cc: Annotated[Optional[str], Query(max_length=2, min_length=2)] = None,
    test_name: Annotated[Optional[str], Query()] = None,
    since: Annotated[Optional[date], Query()] = None,
    until: Annotated[Optional[date], Query()] = None,
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
    software_name: Annotated[Optional[str], Query()] = None,
    software_version: Annotated[Optional[str], Query()] = None,
    test_version: Annotated[Optional[str], Query()] = None,
    engine_version: Annotated[Optional[str], Query()] = None,
    ooni_run_link_id: Annotated[Optional[str], Query()] = None,
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings),
) -> ListObservationsResponse:
    if since is None:
        since = date.today() - timedelta(days=7)
    if until is None:
        until = date.today()

    q_args = {}
    and_clauses = []
    if report_id is not None:
        q_args["report_id"] = report_id
        and_clauses.append("report_id = %(report_id)s")
    if probe_asn is not None:
        probe_asn = parse_probe_asn(probe_asn)
        q_args["probe_asn"] = probe_asn
        and_clauses.append("probe_asn = %(probe_asn)d")
    if probe_cc is not None:
        q_args["probe_cc"] = probe_cc
        and_clauses.append("probe_cc = %(probe_cc)s")

    if software_name is not None:
        q_args["software_name"] = software_name
        and_clauses.append("software_name = %(software_name)s")
    if software_version is not None:
        q_args["software_version"] = software_version
        and_clauses.append("software_version = %(software_version)s")

    if test_name is not None:
        q_args["test_name"] = test_name
        and_clauses.append("test_name = %(test_name)s")
    if test_version is not None:
        q_args["test_version"] = test_version
        and_clauses.append("test_version = %(test_version)s")
    if engine_version is not None:
        q_args["engine_version"] = engine_version
        and_clauses.append("engine_version = %(engine_version)s")

    if ooni_run_link_id is not None:
        q_args["ooni_run_link_id"] = ooni_run_link_id
        and_clauses.append("ooni_run_link_id = %(ooni_run_link_id)s")

    if since is not None:
        q_args["since"] = since
        and_clauses.append("measurement_start_time >= %(since)s")
    if until is not None:
        and_clauses.append("measurement_start_time <= %(until)s")
        q_args["until"] = until

    cols = list(WebObservationEntry.model_json_schema()["properties"].keys())
    q = f"SELECT {','.join(cols)} FROM obs_web"
    if len(and_clauses) > 0:
        q += " WHERE "
        q += " AND ".join(and_clauses)
    q += f" ORDER BY {order_by} {order} LIMIT {limit} OFFSET {offset}"

    t = time.perf_counter()
    rows = db.execute(q, q_args)

    results: List[ObservationEntry] = []
    if rows and isinstance(rows, list):
        for row in rows:
            d = dict(zip(cols, row))
            results.append(WebObservationEntry(**d))

    response = ListObservationsResponse(
        metadata=ResponseMetadata(
            count=-1,
            current_page=math.ceil(offset / limit) + 1,
            limit=limit,
            next_url=f"{settings.base_url}/api/v1/observations?offset={offset+limit}&limit={limit}",
            offset=offset,
            pages=-1,
            query_time=time.perf_counter() - t,
        ),
        results=results,
    )

    return response
