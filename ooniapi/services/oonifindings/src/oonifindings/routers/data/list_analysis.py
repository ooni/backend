from datetime import date, datetime, timedelta, timezone
import logging
import math
from time import time
from typing import List, Literal, Optional, Union
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from pydantic.functional_validators import AfterValidator
from typing_extensions import Annotated

from ...common.dependencies import get_settings
from ...dependencies import get_clickhouse_session
from .utils import SinceUntil, test_name_to_group, utc_30_days_ago, utc_today

log = logging.getLogger(__name__)

from fastapi import APIRouter

router = APIRouter()

# This mapping is used to map ooni/data columns onto the existing data format.
# TODO(arturo): add a check to ensure we aren't mapping stuff onto the same key
OONI_DATA_COLS_REMAP = {
    "measurement_uid": "measurement_uid",
    "observation_id_list": None,
    "timeofday": "measurement_start_time",
    "created_at": None,
    "location_network_type": "network_type",
    "location_network_asn": "probe_asn",
    "location_network_cc": "probe_cc",
    "location_network_as_org_name": "probe_as_org_name",
    "location_network_as_cc": "probe_as_cc",
    "location_resolver_asn": "resolver_asn",
    "location_resolver_as_org_name": "resolver_as_org_name",
    "location_resolver_as_cc": "resolver_as_cc",
    "location_resolver_cc": "resolver_cc",
    "location_blocking_scope": "blocking_scope",
    "target_nettest_group": "nettest_group",
    "target_category": "category_code",
    "target_name": "target_name",
    "target_domain_name": "domain",
    "target_detail": "target_detail",
    "loni_ok_value": "loni_ok_value",
    "loni_down_keys": "loni_down_keys",
    "loni_down_values": "loni_down_values",
    "loni_blocked_keys": "loni_blocked_keys",
    "loni_blocked_values": "loni_blocked_values",
    "loni_ok_keys": "loni_ok_keys",
    "loni_ok_values": "loni_ok_values",
    "loni_list": "loni_list",
    "analysis_transcript_list": None,
    "measurement_count": "measurement_count",
    "observation_count": "observation_count",
    "vp_count": "vp_count",
    "anomaly": "anomaly",
    "confirmed": "confirmed",
}
OONI_DATA_COLS_REMAP_INV = {v: k for k, v in OONI_DATA_COLS_REMAP.items()}


class ResponseMetadata(BaseModel):
    count: int
    current_page: int
    limit: int
    next_url: str
    offset: int
    pages: int
    query_time: float


class MeasurementEntry(BaseModel):
    measurement_uid: str
    measurement_start_time: datetime
    network_type: str
    probe_asn: int
    probe_cc: str
    probe_as_org_name: str
    probe_as_cc: str
    resolver_asn: int
    resolver_as_org_name: str
    resolver_as_cc: str
    resolver_cc: str
    blocking_scope: Optional[str]
    nettest_group: str
    category_code: str
    target_name: str
    domain: str
    target_detail: str
    loni_ok_value: float
    loni_down_keys: list
    loni_down_values: list
    loni_blocked_keys: list
    loni_blocked_values: list
    loni_ok_keys: list
    loni_ok_values: list
    loni_list: str
    measurement_count: int
    observation_count: int
    vp_count: int
    anomaly: int
    confirmed: int


class ListMeasurementsResponse(BaseModel):
    metadata: ResponseMetadata
    results: List[MeasurementEntry]


@router.get("/v1/analysis", tags=["analysis", "list_data"])
async def list_measurements(
    report_id: Annotated[Optional[str], Query()] = None,
    probe_asn: Annotated[Union[int, str, None], Query()] = None,
    probe_cc: Annotated[Optional[str], Query(max_length=2, min_length=2)] = None,
    test_name: Annotated[Optional[str], Query()] = None,
    since: SinceUntil = utc_30_days_ago(),
    until: SinceUntil = utc_today(),
    order_by: Annotated[
        Literal[
            "test_start_time",
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
    anomaly: Annotated[Optional[bool], Query()] = None,
    confirmed: Annotated[Optional[bool], Query()] = None,
    failure: Annotated[Optional[bool], Query()] = None,
    category_code: Annotated[Optional[str], Query()] = None,
    software_version: Annotated[Optional[str], Query()] = None,
    test_version: Annotated[Optional[str], Query()] = None,
    engine_version: Annotated[Optional[str], Query()] = None,
    ooni_run_link_id: Annotated[Optional[str], Query()] = None,
    db=Depends(get_clickhouse_session),
    settings=Depends(get_settings),
) -> ListMeasurementsResponse:
    cols = list(OONI_DATA_COLS_REMAP.keys())
    q_args = {}
    and_clauses = []
    if report_id is not None:
        q_args["report_id"] = report_id
        and_clauses.append("report_id = %(report_id)s")
    if probe_asn is not None:
        if isinstance(probe_asn, str) and probe_asn.startswith("AS"):
            probe_asn = int(probe_asn[2:])
        q_args["probe_asn"] = probe_asn
        and_clauses.append("location_network_asn = %(probe_asn)d")
    if probe_cc is not None:
        q_args["probe_cc"] = probe_cc
        and_clauses.append("location_network_cc = %(probe_cc)s")
    if test_name is not None:
        q_args["test_name"] = test_name_to_group(test_name)
        and_clauses.append("target_nettest_group = %(test_name)s")
    if category_code is not None:
        q_args["category_code"] = category_code
        and_clauses.append("target_category_code = %(category_code)s")

    if software_version is not None:
        # q_args["software_version"] = software_version
        pass
    if test_version is not None:
        # q_args["test_version"] = test_version
        pass
    if engine_version is not None:
        # q_args["engine_version"] = engine_version
        pass

    if ooni_run_link_id is not None:
        # q_args["ooni_run_link_id"] = ooni_run_link_id
        pass

    if since is not None:
        q_args["since"] = since
        and_clauses.append("timeofday >= %(since)s")
    if until is not None:
        and_clauses.append("timeofday <= %(until)s")
        q_args["until"] = until

    if anomaly is True:
        and_clauses.append("arraySum(loni_blocked_values) > 0.5")
    elif anomaly is False:
        and_clauses.append("arraySum(loni_blocked_values) <= 0.5")

    if confirmed is True:
        and_clauses.append("arraySum(loni_blocked_values) == 1.0")

    if failure is False:
        # TODO(arturo): how do we map this onto failure?
        pass

    q = f"SELECT {','.join(cols)} FROM measurement_experiment_result"
    if len(and_clauses) > 0:
        q += " WHERE "
        q += " AND ".join(and_clauses)
    q += f" ORDER BY {OONI_DATA_COLS_REMAP_INV.get(order_by)} {order} LIMIT {limit} OFFSET {offset}"

    t = time.perf_counter()
    log.info(f"running query {q} with {q_args}")
    rows = db.execute(q, q_args)

    results: List[MeasurementEntry] = []
    if rows and isinstance(rows, list):
        for row in rows:
            d = dict(zip(cols, row))
            for old_key, new_key in OONI_DATA_COLS_REMAP.items():
                value = d.pop(old_key)
                if new_key is None:
                    continue
                d[new_key] = value

            results.append(MeasurementEntry(**d))

    response = ListMeasurementsResponse(
        metadata=ResponseMetadata(
            count=-1,
            current_page=math.ceil(offset / limit) + 1,
            limit=limit,
            next_url=f"{settings.base_url}/api/v1/measurements?offset=100&limit=100",
            offset=offset,
            pages=-1,
            query_time=t.s,
        ),
        results=results,
    )

    return response
