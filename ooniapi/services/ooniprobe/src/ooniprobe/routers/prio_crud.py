import logging

from typing import List, Optional, Tuple

from fastapi import Response, APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import sql as sa

from ooniprobe.prio import compute_priorities, generate_test_list
from ooniprobe.dependencies import ClickhouseDep
from ooniprobe.common.clickhouse_utils import query_click
from ooniprobe.common.utils import convert_to_csv

router = APIRouter()

log = logging.getLogger(__name__)


class PrioritizationType(BaseModel):
    anomaly_perc: Optional[str] = Field(description="Anomaly percent")
    category_code: Optional[str] = Field(description="Category code")
    cc: Optional[str] = Field(description="Country Code")
    domain: Optional[str] = Field(description="Domain or wildcard (*)")
    msmt_cnt: Optional[int] = Field(description="msmt_cnt")
    priority: Optional[int] = Field("Priority weight")
    url: Optional[str] = Field("URL or wildcard (*)")


@router.get(
    "/_/show_countries_prioritization", tags=["prioritization"], response_model=None
)
def show_countries_prioritization(
    clickhouse: ClickhouseDep,
    format: Optional[str] = Query(
        default="JSON", description="Format of response, CSV or JSON"
    ),
) -> List[PrioritizationType]:
    sql = """
    SELECT domain, url, cc, category_code, msmt_cnt, anomaly_perc
    FROM citizenlab
    LEFT JOIN (
        SELECT input, probe_cc, count() AS msmt_cnt,
            toInt8(countIf(anomaly = 't') / msmt_cnt * 100) AS anomaly_perc
        FROM fastpath
        WHERE measurement_start_time > now() - interval 1 week
        AND measurement_start_time < now()
        GROUP BY input, probe_cc
    ) AS x ON x.input = citizenlab.url AND x.probe_cc = UPPER(citizenlab.cc)
    """
    cz = tuple(query_click(clickhouse, sa.text(sql), {}))  # cc can be "ZZ" here

    # Fetch priority rules and apply them to URLs
    sql = "SELECT category_code, cc, domain, url, priority FROM url_priorities"
    prio_rules = tuple(query_click(clickhouse, sa.text(sql), {}))
    li = compute_priorities(cz, prio_rules)
    for x in li:
        x.pop("weight")
        x["cc"] = x["cc"].upper()

    li = sorted(li, key=lambda x: (x["cc"], -x["priority"]))

    if len(li) == 0:
        raise HTTPException(status_code=400, detail="no data")

    if format.upper() == "CSV":
        csv_data = convert_to_csv(li)
        response = Response(content=csv_data, media_type="text/csv")
        return response

    return li


class DebugPrioritization(BaseModel):
    test_items: List
    entries: Tuple
    prio_rules: Tuple


@router.get(
    "/_/debug_prioritization",
    tags=["prioritization"],
    response_model=DebugPrioritization,
)
def debug_prioritization(
    clickhouse: ClickhouseDep,
    probe_cc: Optional[str] = Query(description="2-letter Country-Code", default="ZZ"),
    category_codes: str = Query(
        description="Comma separated list of uppercase URL categories"
    ),
    probe_asn: int = Query(description="Probe ASN"),
    limit: Optional[int] = Query(
        description="Maximum number of URLs to return", default=-1
    ),
) -> DebugPrioritization:

    test_items, entries, prio_rules = generate_test_list(
        clickhouse, probe_cc, category_codes, probe_asn, limit, True
    )
    return {"test_items": test_items, "entries": entries, "prio_rules": prio_rules}
