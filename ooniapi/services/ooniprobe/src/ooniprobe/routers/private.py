"""
prefix: /api/_

In here live private API endpoints for use only by OONI services. You should
not rely on these as they are likely to change, break in unexpected ways. Also
there is no versioning on them.
"""
from datetime import date, datetime, timedelta, timezone
from itertools import product

from urllib.parse import urljoin, urlencode
from typing import Annotated, Dict, Any, Tuple, List, Optional

import logging
import math

from sqlalchemy import sql

from fastapi import APIRouter, Depends, Header, Request, Response, Query
from pydantic_extra_types.country import CountryAlpha2
from pydantic import AnyUrl, Field

from .v1.probe_services import probe_geoip, generate_test_helpers_conf
from ..common.clickhouse_utils import query_click, query_click_one_row
from ..common.dependencies import role_required, ClickhouseDep
from ..common.prio import generate_test_list
from ..common.routers import BaseModel
from ..metrics import Metrics
from ..countries import lookup_country
from ..data import dnscheck_inputs, stunreachability_inputs
from ..utils import generate_report_id


# The private API is exposed under the prefix /api/_
# e.g. https://api.ooni.io/api/_/test_names
router = APIRouter(prefix="/_")

log = logging.getLogger(__name__)

# TODO: configure tags for HTTP caching across where useful

TEST_GROUPS = {
    "websites": ["web_connectivity"],
    "im": ["facebook_messenger", "signal", "telegram", "whatsapp"],
    "middlebox": ["http_invalid_request_line", "http_header_field_manipulation"],
    "performance": ["ndt", "dash"],
    "circumvention": [
        "bridge_reachability",
        "meek_fronted_requests_test",
        "vanilla_tor",
        "tcp_connect",
        "psiphon",
        "tor",
        "torsf",
        "riseupvpn",
    ],
    "legacy": [
        "http_requests",
        "dns_consistency",
        "http_host",
        "multi_protocol_traceroute",
    ],
    "experimental": [
        "urlgetter",
        "dnscheck",
        "stunreachability",
    ],
}


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days)):
        yield start_date + timedelta(n)


def expand_dates(li):
    """Replaces 'date' key in a list of dict"""
    for i in li:
        i["date"] = i["date"].strftime("%Y-%m-%dT00:00:00+00:00")


class ASNCount(BaseModel):
    date: datetime = Field(..., description="Timestamp for the measurement (ISO 8601).")
    value: int = Field(..., description="Count of unique ASN seen.")
    model_config = {
        "json_encoders": { datetime: lambda dt: dt.astimezone(timezone.utc).replace(microsecond=0).isoformat() }
    }


@router.get("/asn_by_month", tags=["private"], response_model=List[ASNCount])
def api_private_asn_by_month(
    clickhouse: ClickhouseDep,
) -> List[ASNCount]:
    """Network count by month
    """

    q = """SELECT
        COUNT(DISTINCT(probe_asn)) AS value,
        toStartOfMonth(measurement_start_time) AS date
    FROM fastpath
    WHERE measurement_start_time < toStartOfMonth(addMonths(now(), 1))
    AND measurement_start_time > toStartOfMonth(subtractMonths(now(), 24))
    GROUP BY date ORDER BY date
    """
    li = list(query_click(clickhouse, q, {}))
    expand_dates(li)
    return [ASNCount(**item) for item in li]


class CountryCount(BaseModel):
    date: datetime = Field(..., description="Timestamp for the measurement (ISO 8601).")
    value: int = Field(..., description="Count of unique countries seen.")

    model_config = {
        "json_encoders": { datetime: lambda dt: dt.astimezone(timezone.utc).replace(microsecond=0).isoformat() }
    }



@router.get("/countries_by_month", tags=["private"], response_model=List[CountryCount])
def api_private_countries_by_month(
    clickhouse: ClickhouseDep,
) -> List[CountryCount]:
    """Countries count by month
    """
    q = """SELECT
        COUNT(DISTINCT(probe_cc)) AS value,
        toStartOfMonth(measurement_start_time) AS date
    FROM fastpath
    WHERE measurement_start_time < toStartOfMonth(addMonths(now(), 1))
    AND measurement_start_time > toStartOfMonth(subtractMonths(now(), 24))
    GROUP BY date ORDER BY date
    """
    li = list(query_click(clickhouse, q, {}))
    expand_dates(li)
    return [CountryCount(**item) for item in li]


class TestName(BaseModel):
    id: str = Field(..., description="test id")
    name: str = Field(..., description="test name")


class TestNameResponse(BaseModel):
    test_names: List[TestName]


@router.get("/test_names", tags=["private"], response_model=TestNameResponse)
def api_private_test_names() -> TestNameResponse:
    """Provides test names and descriptions to Explorer
    """
    # TODO: eventually drop this, once we see nobody is using it
    TEST_NAMES = {
        "bridge_reachability": "Bridge Reachability",
        "dash": "DASH",
        "dns_consistency": "DNS Consistency",
        "dnscheck": "DNS Check",
        "facebook_messenger": "Facebook Messenger",
        "http_header_field_manipulation": "HTTP Header Field Manipulation",
        "http_host": "HTTP Host",
        "http_invalid_request_line": "HTTP Invalid Request Line",
        "http_requests": "HTTP Requests",
        "meek_fronted_requests_test": "Meek Fronted Requests",
        "multi_protocol_traceroute": "Multi Protocol Traceroute",
        "ndt": "NDT",
        "psiphon": "Psiphon",
        "riseupvpn": "RiseupVPN",
        "signal": "Signal",
        "stunreachability": "STUN Reachability",
        "tcp_connect": "TCP Connect",
        "telegram": "Telegram",
        "tor": "Tor",
        "torsf": "Tor Snowflake",
        "urlgetter": "URL Getter",
        "vanilla_tor": "Vanilla Tor",
        "web_connectivity": "Web Connectivity",
        "whatsapp": "WhatsApp",
    }
    return TestNameResponse(test_names=[TestName(id=k, name=v) for k, v in TEST_NAMES.items()])


class CountryStat(BaseModel):
    alpha_2: CountryAlpha2 = Field(..., description="Country Code")
    count: int = Field(..., description="Measurement count")
    name: str = Field(..., description="Country Name")


class CountryStatResponse(BaseModel):
    countries: List[CountryStat] = Field(..., description="List of countries")


@router.get("/countries", tags=["private"], response_model=CountryStatResponse)
def api_private_countries(
    clickhouse: ClickhouseDep,
) -> CountryStatResponse:
    """Summary of countries
    """
    q = """
    SELECT probe_cc, COUNT() AS measurement_count
    FROM fastpath
    GROUP BY probe_cc ORDER BY probe_cc
    """
    c = []
    rows = query_click(clickhouse, q, {})
    for r in rows:
        try:
            name = lookup_country(r["probe_cc"])
            c.append(
                CountryStat(alpha_2=r["probe_cc"], name=name, count=r["measurement_count"])
            )
        except KeyError:
            pass

    return CountryStatResponse(countries=c)


@router.get(
    "/quotas_summary",
    response_model=List[CountryStat],
    tags=["private"],
    dependencies=[Depends(role_required(["admin"]))],
)
def api_private_quotas_summary() -> List[CountryStat]:
    """Summary on rate-limiting quotas.
    [(first ipaddr octet, remaining daily quota), ... ]
    """
    # XXX: add limiter to ooniapi
    #return nocachejson(current_app.limiter.get_lowest_daily_quotas_summary())
    raise NotImplemented


class CheckReportIDResponse(BaseModel):
    v: int = Field(..., description="version number of this response")
    found: bool = Field(..., description="Report found")


@router.get("/check_report_id",
    response_model=CheckReportIDResponse,
    tags=["private"],
)
def check_report_id() -> CheckReportIDResponse:
    """Legacy. Used to check if a report_id existed in the fastpath table.
    Used by https://github.com/ooni/probe/issues/1034. Always returns True.
    """
    return CheckReportIDResponse(v=0, found=True)


def last_30days(begin=31, end=1):
    first_day = datetime.now() - timedelta(begin)
    first_day = datetime(first_day.year, first_day.month, first_day.day)

    last_day = datetime.now() - timedelta(end)
    last_day = datetime(last_day.year, last_day.month, last_day.day)

    for d in daterange(first_day, last_day):
        yield d.strftime("%Y-%m-%d")


def pivot_test_coverage(rows, test_group_names, days):
    # "pivot": create a datapoint for each test group, for each day
    # lookup map (tg, day) -> cnt
    tmp = {}
    for r in rows:
        day = r["measurement_start_day"].strftime("%Y-%m-%d")
        k = (r["test_group"], day)
        tmp[k] = r["msmt_cnt"]

    test_coverage = [
        dict(
            count=tmp.get((tg, day), 0),
            test_day=day,
            test_group=tg,
        )
        for tg in test_group_names
        for day in days
    ]
    return test_coverage


def get_recent_test_coverage_ch(clickhouse, probe_cc):
    """Returns
    [{"count": 4888, "test_day": "2021-10-16", "test_group": "websites"}, ... ]
    """
    q = "SELECT DISTINCT(test_group) FROM test_groups ORDER BY test_group"
    rows = query_click(clickhouse, sql.text(q), {})
    test_group_names = [r["test_group"] for r in rows]

    q = """SELECT
        toDate(measurement_start_time) as measurement_start_day,
        test_group,
        COUNT() as msmt_cnt
    FROM fastpath
    ANY LEFT JOIN test_groups USING (test_name)
    WHERE measurement_start_day >= today() - interval 32 day
    AND measurement_start_day < today() - interval 2 day
    AND probe_cc = :probe_cc
    GROUP BY measurement_start_day, test_group
    """
    rows = query_click(clickhouse, sql.text(q), dict(probe_cc=probe_cc))
    rows = tuple(rows)
    l30d = tuple(last_30days(32, 2))
    return pivot_test_coverage(rows, test_group_names, l30d)


def get_recent_network_coverage_ch(clickhouse, probe_cc, test_groups):
    """Count ASNs with at least one measurements, grouped by day,
    for a given CC, and filtered by test groups
    Return [{"count": 58, "test_day": "2021-10-16" }, ... ]"""
    s = """SELECT
        toDate(measurement_start_time) AS test_day,
        COUNT(DISTINCT probe_asn) as count
    FROM fastpath
    WHERE test_day >= today() - interval 31 day
        AND test_day < today() - interval 1 day
        AND probe_cc = :probe_cc
        --mark--
    GROUP BY test_day ORDER BY test_day
    WITH FILL
        FROM today() - interval 31 day
        TO today() - interval 1 day
    """
    if test_groups:
        assert isinstance(test_groups, list)
        test_names = set()
        for tg in test_groups:
            tnames = TEST_GROUPS.get(tg, [])
            test_names.update(tnames)
        test_names = sorted(test_names)
        s = s.replace("--mark--", "AND test_name IN :test_names")
        d = {"probe_cc": probe_cc, "test_names": test_names}

    else:
        s = s.replace("--mark--", "")
        d = {"probe_cc": probe_cc}

    return query_click(clickhouse, sql.text(s), d)


class NetworkCoveragePoint(BaseModel):
    test_day: date = Field(..., description="Date for the measurement (YYYY-MM-DD)")
    count: int = Field(..., description="Count of unique ASNs seen that day")


class TestCoveragePoint(BaseModel):
    test_day: date = Field(..., description="Date for the measurement (YYYY-MM-DD)")
    test_group: str = Field(..., description="Test group name")
    count: int = Field(..., description="Number of measurements for this test group on that day")


class TestCoverageResponse(BaseModel):
    network_coverage: List[NetworkCoveragePoint] = Field(..., description="Daily network coverage (ASNs per day)")
    test_coverage: List[TestCoveragePoint] = Field(..., description="Per-test-group coverage per day")


@router.get("/test_coverage", response_model=TestCoverageResponse, tags=["private"])
def api_private_test_coverage(
    clickhouse: ClickhouseDep,
    probe_cc: CountryAlpha2 = Query(..., description="Country Code"),
    test_groups: str = Query(None, description="Comma-separated list of test group keys to filter results")
) -> TestCoverageResponse:
    """Return number of measurements per day across test categories
    """
    # TODO: merge the two queries into one?
    # TODO: remove test categories or move aggregation to the front-end?
    if test_groups is not None:
        test_groups = test_groups.split(",")

    tc = get_recent_test_coverage_ch(clickhouse, probe_cc)
    nc = get_recent_network_coverage_ch(clickhouse, probe_cc, test_groups)
    validated = TestCoverageResponse(network_coverage=nc, test_coverage=tc)
    return validated


class MeasurementsByASN(BaseModel):
    count: int = Field(..., description="Number of measurments for eachnetworks in country")
    probe_asn: str = Field(..., description="Autonomous System Number")


@router.get("/website_networks", response_model=List[MeasurementsByASN], tags=["private"])
def api_private_website_network_tests(
    clickhouse: ClickhouseDep,
    probe_cc: CountryAlpha2 = Query(..., description="Country Code")
) -> List[MeasurementsByASN]:
    """Daily counts of website measurements per ASN for the past 31 days, returned as a list of (probe_asn, count) ordered by count descending."""
    s = """SELECT
        COUNT() AS count,
        probe_asn
        FROM fastpath
        WHERE
            measurement_start_time >= today() - interval '31 day'
        AND measurement_start_time < today()
        AND probe_cc = :probe_cc
        GROUP BY probe_asn
        ORDER BY count DESC
        """
    results = query_click(clickhouse, sql.text(s), {"probe_cc": probe_cc})
    validated: List[MeasurementsByASN] = [MeasurementsByASN(**x) for x in results]
    return validated


class DayStats(BaseModel):
    test_day: date = Field(..., description="Date for the aggregated counts (YYYY-MM-DD)")
    anomaly_count: int = Field(..., description="Number of measurements flagged as anomalies on this day")
    confirmed_count: int = Field(..., description="Number of anomalies confirmed on this day")
    failure_count: int = Field(..., description="Number of measurements that failed on this day")
    total_count: int = Field(..., description="Total number of measurements for this day")


class WebsiteStatsResponse(BaseModel):
    results: List[DayStats] = Field(..., description="Daily aggregated statistics for the queried website, country, and ASN (ordered by day)")


@router.get("/website_stats", response_model=WebsiteStatsResponse, tags=["private"])
def api_private_website_stats(
    clickhouse: ClickhouseDep,
    input: AnyUrl = Query(..., description="Website to query stats"),
    probe_cc: CountryAlpha2 = Query(..., description="Country Code"),
    probe_asn: int = Query(..., description="ASN (integer)"),
) -> WebsiteStatsResponse:
    """Daily aggregated website measurement statistics (anomalies, confirmations, failures, and totals) for the past 31 days."""
    # uses_pg_index counters_day_cc_asn_input_idx a BRIN index was not used at
    # all, but BTREE on (measurement_start_day, probe_cc, probe_asn, input)
    # made queries go from full scan to 50ms
    url = input

    s = """SELECT
        toDate(measurement_start_time) AS test_day,
        countIf(anomaly = 't') as anomaly_count,
        countIf(confirmed = 't') as confirmed_count,
        countIf(msm_failure = 't') as failure_count,
        COUNT() AS total_count
        FROM fastpath
        WHERE measurement_start_time >= today() - interval '31 day'
        AND measurement_start_time < today()
        AND probe_cc =  :probe_cc
        AND probe_asn = :probe_asn
        AND input = :input
        GROUP BY test_day ORDER BY test_day
    """
    d = {"probe_cc": probe_cc, "probe_asn": probe_asn, "input": url}
    results = query_click(clickhouse, sql.text(s), d)
    return WebsiteStatsResponse(result=results)


class WebsiteURLItem(BaseModel):
    input: AnyUrl = Field(..., description="Tested URL")
    anomaly_count: int = Field(..., description="Number of measurements flagged as anomalies for this URL in the past 31 days")
    confirmed_count: int = Field(..., description="Number of anomalies confirmed for this URL in the past 31 days")
    failure_count: int = Field(..., description="Number of measurements that failed for this URL in the past 31 days")
    total_count: int = Field(..., description="Total number of measurements for this URL in the past 31 days")


class PaginationMetadata(BaseModel):
    offset: int = Field(..., description="Current result offset")
    limit: int = Field(..., description="Maximum number of results returned")
    current_page: int = Field(..., description="Current page number (1-based)")
    total_count: int = Field(..., description="Total number of matching URLs")
    next_url: Optional[AnyUrl] = Field(None, description="URL for the next page of results, or null if none")


class WebsiteURLsResponse(BaseModel):
    metadata: PaginationMetadata = Field(..., description="Pagination metadata for the results")
    results: List[WebsiteURLItem] = Field(..., description="List of URL statistics for the requested CC/ASN")


@router.get("/website_urls", response_model=WebsiteURLsResponse, tags=["private"])
def api_private_website_test_urls(
    clickhouse: ClickhouseDep,
    probe_cc: CountryAlpha2 = Query(..., description="Country Code"),
    probe_asn: str = Query(..., description="ASN, e.g. AS1234"),
    limit: int = Query(10, description="Limit results"),
    offset: int = Query(0, description="Offset results")
) -> WebsiteURLsResponse:
    """Paginated list of tested URLs with per-URL counts (anomalies, confirmations, failures, totals) for the past 31 days."""
    # TODO optimize or remove
    if limit <= 0:
        limit = 10

    probe_asn = int(probe_asn.replace("AS", ""))

    # Count how many distinct inputs we have in this CC / ASN / period
    s = """
        SELECT COUNT(DISTINCT(input)) as input_count
        FROM fastpath
        WHERE measurement_start_time >= today() - interval '31 day'
        AND measurement_start_time < today()
        AND test_name = 'web_connectivity'
        AND probe_cc = :probe_cc
        AND probe_asn = :probe_asn
    """
    q = query_click_one_row(clickhouse, sql.text(s), dict(probe_cc=probe_cc, probe_asn=probe_asn))
    total_count = q["input_count"] if q else 0

    # Group msmts by CC / ASN / period with LIMIT and OFFSET
    s = """SELECT input,
        countIf(anomaly = 't') as anomaly_count,
        countIf(confirmed = 't') as confirmed_count,
        countIf(msm_failure = 't') as failure_count,
        COUNT() AS total_count
        FROM fastpath
        WHERE measurement_start_time >= today() - interval '31 day'
        AND measurement_start_time < today()
        AND test_name = 'web_connectivity'
        AND probe_cc =  :probe_cc
        AND probe_asn = :probe_asn
        GROUP BY input
        ORDER BY confirmed_count DESC, total_count DESC,
                anomaly_count DESC, input ASC
        LIMIT :limit
        OFFSET :offset
        """
    d = {
        "probe_cc": probe_cc,
        "probe_asn": probe_asn,
        "limit": limit,
        "offset": offset,
    }
    results = query_click(clickhouse, sql.text(s), d)
    current_page = math.ceil(offset / limit) + 1
    metadata = {
        "offset": offset,
        "limit": limit,
        "current_page": current_page,
        "total_count": total_count,
        "next_url": None,
    }

    # Create next_url
    if len(results) >= limit:
        args = dict(
            limit=limit,
            offset=offset + limit,
            probe_asn=probe_asn,
            probe_cc=probe_cc,
        )
        # TODO: remove BASE_URL?
        next_url = urljoin(
            current_app.config["BASE_URL"],
            "/api/_/website_urls?%s" % urlencode(args),
        )
        metadata["next_url"] = next_url

    # validate and return
    return WebsiteURLsResponse(metadata=metadata, results=results)


class NetworkStat(BaseModel):
    failure_count: int = Field(..., description="Number of failed measurements for this ASN")
    last_tested: Optional[date] = Field(None, description="Date of the most recent measurement (YYYY-MM-DD)")
    probe_asn: int = Field(..., description="Autonomous System Number (integer)")
    total_count: int = Field(..., description="Total number of measurements for this ASN")
    success_count: int = Field(..., description="Number of successful measurements for this ASN")
    test_runtime_avg: Optional[float] = Field(None, description="Average test runtime in seconds for this ASN")
    test_runtime_max: Optional[float] = Field(None, description="Maximum test runtime in seconds for this ASN")
    test_runtime_min: Optional[float] = Field(None, description="Minimum test runtime in seconds for this ASN")


class TorStatsResponse(BaseModel):
    last_tested: Optional[date] = Field(None, description="Most recent test date across all networks (YYYY-MM-DD)")
    networks: List[NetworkStat] = Field(..., description="List of per-ASN Tor test statistics")
    notok_networks: int = Field(..., description="Number of networks considered 'not OK' (low success rate)")


@router.get("/vanilla_tor_stats", response_model=TorStatsResponse, tags=["private"])
def api_private_vanilla_tor_stats(
    clickhouse: ClickhouseDep,
    probe_cc: str = Query(..., description="Country Code")
) -> TorStatsResponse:
    """Per-ASN Tor measurement statistics for the given country over the last 6 months, including counts, last-tested date, and a tally of networks with low success rates."""
    try:
        CountryAlpha2(probe_cc)
    except Exception:
        raise
    blocked = 0
    nets = []
    s = """SELECT
        countIf(msm_failure = 't') as failure_count,
        toDate(MAX(measurement_start_time)) AS last_tested,
        probe_asn,
        COUNT() as total_count,
        total_count - countIf(anomaly = 't') AS success_count
        FROM fastpath
        WHERE measurement_start_time > today() - INTERVAL 6 MONTH
        AND probe_cc =  :probe_cc
        GROUP BY probe_asn
    """
    q = query_click(clickhouse, sql.text(s), {"probe_cc": probe_cc})
    extras = {
        "test_runtime_avg": None,
        "test_runtime_max": None,
        "test_runtime_min": None,
    }
    for n in q:
        n.update(extras)
        nets.append(n)
        if n["total_count"] > 5:
            if float(n["success_count"]) / float(n["total_count"]) < 0.6:
                blocked += 1

    if not nets:
        return TorStatsResponse(
            last_tested=None,
            networks=[],
            notok_networks=0,
        )

    lt = max(n["last_tested"] for n in nets)
    return TorStatsResponse(
        last_tested=lt,
        networks=nets,
        notok_networks=blocked,
    )


class NetworkEntry(BaseModel):
    asn: int = Field(..., description="Autonomous System Number (integer)")
    name: str = Field(..., description="Network/ASN name")
    total_count: int = Field(..., description="Total number of measurements for this ASN and test")
    last_tested: date = Field(..., description="Date of the most recent measurement (YYYY-MM-DD)")


class IMNetworkStats(BaseModel):
    anomaly_networks: List[NetworkEntry] = Field(..., description="List of networks showing anomalous behaviour for this test")
    ok_networks: List[NetworkEntry] = Field(..., description="List of networks considered OK for this test")
    last_tested: date = Field(..., description="Most recent measurement date across networks for this test")


@router.get("/im_networks", response_model=Dict[str, IMNetworkStats], tags=["private"])
def api_private_im_networks(
    clickhouse: ClickhouseDep,
    probe_cc: CountryAlpha2 = Query(..., description="Country Code")
) -> Dict[str, IMNetworkStats]:
    """Per-test instant messaging network statistics (per-ASN totals and last-tested date) for the past 31 days, keyed by test name."""
    s = """SELECT
    COUNT() AS total_count,
    '' AS name,
    toDate(MAX(measurement_start_time)) AS last_tested,
    probe_asn,
    test_name
    FROM fastpath
    WHERE measurement_start_time >= today() - interval 31 day
    AND measurement_start_time < today()
    AND probe_cc = :probe_cc
    AND test_name IN :test_names
    GROUP BY test_name, probe_asn
    ORDER BY test_name ASC, total_count DESC
    """
    test_names = ["facebook_messenger", "signal", "telegram", "whatsapp"]
    q = query_click(clickhouse, sql.text(s), {"probe_cc": probe_cc, "test_names": test_names})
    results: Dict[str, IMNetworkStats] = {}
    for r in q:
        # get stats for test_name or create a new IMNetworksStats
        stats = results.get(r["test_name"], IMNetworkStats(anomaly_networks=[], ok_networks=[], last_tested=None))

        # create and add a new entry
        entry = NetworkEntry(asn=r["probe_asn"], name="", total_count=r["total_count"], last_tested=r["last_tested"])
        stats.ok_networks.append(entry)

        # XXX: anomaly_networks appears unused

        # update last_tested if it is the latest measurement
        if stats.last_tested < entry.last_tested:
            stats.last_tested = entry.last_tested

        # save the object in results
        results[stats.test_name] = stats

    return results


def isomid(d) -> str:
    """Returns 2020-08-01T00:00:00+00:00"""
    return f"{d}T00:00:00+00:00"


class IMStatsItem(BaseModel):
    anomaly_count: Optional[int] = Field(None, description="Number of measurements flagged as anomalies for that day")
    test_day: datetime = Field(..., description="Timestamp for the day (ISO 8601, midnight UTC)")
    total_count: int = Field(..., description="Total number of measurements for that day")
    model_config = {
        "json_encoders": { datetime: lambda dt: dt.astimezone(timezone.utc).replace(microsecond=0).isoformat() }
    }


class IMStatsResponse(BaseModel):
    results: List[IMStatsItem] = Field(..., description="Daily IM statistics for the requested ASN/CC/test (last 31 days)")


@router.get("/im_stats", response_model=IMStatsResponse, tags=["private"])
def api_private_im_stats(
    clickhouse: ClickhouseDep,
    probe_asn: str = Query(..., description="ASN, e.g. AS1234"),
    probe_cc: CountryAlpha2 = Query(..., description="Country Code"),
    test_name: str = Query(..., description="Test name")
) -> IMStatsResponse:
    """Daily instant messaging measurement totals (and optional anomaly counts) for the past 31 days, for the given ASN, country, and test."""
    test_names = ["facebook_messenger", "signal", "telegram", "whatsapp"]
    if test_name not in test_names:
        raise HTTPException(status_code=400, detail="Invalid test_name")

    probe_asn = int(probe_asn.upper().replace("AS", ""))

    s = """SELECT
        COUNT() as total_count,
        toDate(measurement_start_time) AS test_day
        FROM fastpath
        WHERE probe_cc = :probe_cc
        AND test_name = :test_name
        AND probe_asn = :probe_asn
        AND measurement_start_time >= today() - interval '31 day'
        AND measurement_start_time < today()
        GROUP BY test_day
        ORDER BY test_day
    """
    query_params = {
        "probe_cc": probe_cc,
        "probe_asn": probe_asn,
        "test_name": test_name,
    }
    q = query_click(clickhouse, sql.text(s), query_params)
    tmp = {r["test_day"]: r for r in q}
    items: List[IMStatsItem] = []
    days = [date.today() + timedelta(days=(d - 31)) for d in range(32)]
    for d in days:
        if d in tmp:
            test_day = isomid(tmp[d]["test_day"])
            total_count = tmp[d]["total_count"]
        else:
            test_day = isomid(d)
            total_count = 0
        items.append(IMStatsItem(anomaly_count=None, test_day=test_day, total_count=total_count))

    response = IMStatsResponse(results=items)
    return response


class NetworkStats(BaseModel):
    asn: int = Field(..., description="ASN (int)")
    asn_name: str = Field(..., description="Autonomous System Name")
    download_speed_mbps_median: float = Field(description="Median download speed in megabits")
    upload_speed_mbps_median: float = Field(description="Median upload speed in megabites")
    middlebox_detected: bool = Field(..., description="Middlebox was detected")
    msm_count: float = Field(..., description="FIXME: example: 24596.0")
    rtt_avg: float = Field(..., description="Round Trip Time Average")


class NetworkMetadata(BaseModel):
    current_page: int = Field(1, description="Current page")
    limit: int = Field(10, description="Result limit")
    next_url: Optional[AnyUrl] = Field(None, description="Next URL")
    offset: int = Field(0, description="Result offset")
    total_count: int = Field(0, description="Total results")


class NetworkStatsResponse(BaseModel):
    metadata: NetworkMetadata = Field(..., description="Pagination and result metadata")
    results: List[NetworkStats] = Field(..., description="List of per-ASN network statistics")


@router.get("/network_stats", response_model=NetworkStatsResponse, tags=["private"])
def api_private_network_stats(
    probe_cc: CountryAlpha2 = Query(..., description="Country Code"),
    limit: int = Query(10, description="Limit results"),
    offset: int = Query(0, description="Offset results"),
    clickhouse: ClickhouseDep,
) -> NetworkStatsResponse:

    # TODO: implement the stats from NDT in fastpath and then here

    return NetworkStatsResponse(metadata=NetworkMetadata(), results=[])


class CountryOverviewResponse(BaseModel):
    first_bucket_date: date = Field(..., description="First bucket date YYYY-MM-DD")
    measurement_count: int = Field(..., description="Number of measurements")
    network_count: int = Field(..., description="Number of networks measured")


@router.get("/country_overview", response_model=CountryOverviewResponse, tags=["private"])
def api_private_country_overview(
    clickhouse: ClickhouseDep,
    probe_cc: CountryAlpha2 = Query(..., description="Country Code"),
) -> CountryOverviewResponse:
    """Country-level summary for the requested two-letter code: first available measurement date, total number of measurements since 2012-12-01, and number of distinct ASNs observed (networks)."""
    # TODO: add circumvention_tools_blocked im_apps_blocked
    # middlebox_detected_networks websites_confirmed_blocked
    s = """SELECT
        toDate(MIN(measurement_start_time)) AS first_bucket_date,
        COUNT() AS measurement_count,
        COUNT(DISTINCT probe_asn) AS network_count
        FROM fastpath
        WHERE probe_cc = :probe_cc
        AND measurement_start_time > '2012-12-01'
    """
    r = query_click_one_row(clickhouse, sql.text(s), {"probe_cc": probe_cc})
    assert r
    result = CountryOverviewResponse(
            first_bucket_date=r["first_bucket_date"],
            measurement_count=r["measurement_count"],
            network_count=r["network_count"])
    return result


class GlobalOverviewResponse(BaseModel):
    network_count: int = Field(..., description="Number of networks measured")
    country_count: int = Field(..., description="Number of countries measured")
    measurement_count: int = Field(..., description="Number of total measurements")


@router.get("/global_overview", response_model=GlobalOverviewResponse, tags=["private"])
def api_private_global_overview(
    clickhouse: ClickhouseDep,
) -> GlobalOverviewResponse:
    """Global summary of measurements across all countries: total distinct networks (ASNs), total countries with measurements, and total measurement count (computed from the fastpath table)."""
    q = """SELECT
        COUNT(DISTINCT(probe_asn)) AS network_count,
        COUNT(DISTINCT probe_cc) AS country_count,
        COUNT(*) AS measurement_count
    FROM fastpath
    """
    r = query_click_one_row(clickhouse, q, {})
    assert r
    result = GlobalOverviewResponse(
            network_count=r["network_count"],
            country_count=r["country_count"],
            measurement_count=r["measurement_count"])
    return result


class GlobalOverviewStat(BaseModel):
    date: datetime = Field(..., description="Month start timestamp (ISO 8601, midnight UTC)")
    value: int = Field(..., description="Count value for the month")
    model_config = {
        "json_encoders": { datetime: lambda dt: dt.astimezone(timezone.utc).replace(microsecond=0).isoformat() }
    }


class GlobalOverviewMonthResponse(BaseModel):
    networks_by_month: List[GlobalOverviewStat] = Field(..., description="Monthly distinct network (ASN) counts")
    countries_by_month: List[GlobalOverviewStat] = Field(..., description="Monthly distinct country counts")
    measurements_by_month: List[GlobalOverviewStat] = Field(..., description="Monthly total measurement counts")


@router.get("/global_overview_by_month", response_model=GlobalOverviewMonthResponse, tags=["private"])
def api_private_global_by_month(
    clickhouse: ClickhouseDep,
) -> GlobalOverviewMonthResponse:
    """Monthly global time series for the last two years: distinct networks (ASNs), distinct countries, and total measurements per month (month timestamps are start-of-month)."""
    q = """SELECT
        COUNT(DISTINCT probe_asn) AS networks_by_month,
        COUNT(DISTINCT probe_cc) AS countries_by_month,
        COUNT() AS measurements_by_month,
        toStartOfMonth(measurement_start_time) AS month
        FROM fastpath
        WHERE measurement_start_time > toStartOfMonth(today() - interval 2 year)
        AND measurement_start_time < toStartOfMonth(today() + interval 1 month)
        GROUP BY month ORDER BY month
    """
    rows = query_click(clickhouse, sql.text(q), {})
    rows = list(rows)

    n = [{"date": r["month"], "value": r["networks_by_month"]} for r in rows]
    c = [{"date": r["month"], "value": r["countries_by_month"]} for r in rows]
    m = [{"date": r["month"], "value": r["measurements_by_month"]} for r in rows]
    expand_dates(n)
    expand_dates(c)
    expand_dates(m)
    validated = GlobalOverviewMonthResponse(networks_by_month=n, countries_by_month=c, measurements_by_month=m)
    return validated


class CountryCircumventionStat(BaseModel):
    cnt: int = Field(..., description="Count of measurements")
    probe_cc: CountryAlpha2 = Field(..., description="Country code of probe")


class CircumventionStatsResponse(BaseModel):
    results: Optional[List[CountryCircumventionStat]] = Field(None, description="List of per-country circumvention tool measurement counts over 6 months")
    v: int = Field(..., description="API Response version")


@router.get("/circumvention_stats_by_country", response_model=CircumventionStatsResponse, tags=["private"])
def api_private_circumvention_stats_by_country(
    clickhouse: ClickhouseDep,
) -> CircumventionStatsResponse:
    """Aggregated statistics on protocols used for circumvention, grouped by country. """
    q = """SELECT probe_cc, COUNT(*) as cnt
        FROM fastpath
        WHERE measurement_start_time > today() - interval 6 month
        AND measurement_start_time < today() - interval 1 day
        AND test_name IN ['torsf', 'tor', 'stunreachability', 'psiphon','riseupvpn']
        GROUP BY probe_cc ORDER BY probe_cc
    """
    try:
        result = query_click(clickhouse, sql.text(q), {})
        return CountryCircumVentionStatsResponse(results=result)

    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e), "v": 0})


class CircumventionRuntimeStat(BaseModel):
    test_name: str = Field(..., description="Name of test")
    probe_cc: CountryAlpha2 = Field(..., description="Country code of probe")
    metric_date: date = Field(..., alias="date", description="Date of metric")
    v: Tuple[float, float, int] = Field((), description="(p50, p90, cnt)")


def pivot_circumvention_runtime_stats(rows) -> List[CircumventionRuntimeStat]:
    # "pivot": create a datapoint for each probe_cc/test_name/date
    tmp = {}
    test_names = set()
    ccs = set()
    dates = set()
    for r in rows:
        k = (r["test_name"], r["probe_cc"], r["date"])
        tmp[k] = (r["p50"], r["p90"], r["cnt"])
        test_names.add(k[0])
        ccs.add(k[1])
        dates.add(k[2])

    dates = sorted(dates)
    ccs = sorted(ccs)
    test_names = sorted(test_names)
    no_data = ()
    result = [
        RuntimeStat(test_name=k[0], probe_cc=k[1], date=k[2], v=tmp.get(k, no_data))
        for k in product(test_names, ccs, dates)
    ]
    return result


class CircumventionRuntimeStatsResponse(BaseModel):
    results: List[CircumventionRuntimeStat]
    v: int = Field(..., description="Version of API response")


@router.get("/circumvention_runtime_stats", response_model=CircumventionRuntimeStatsResponse, tags=["private"])
def api_private_circumvention_runtime_stats(
    clickhouse: ClickhouseDep,
) -> CircumventionRuntimeStatsResponse:
    """Runtime statistics on protocols used for circumvention, grouped by date, country, test_name. """
    q = """SELECT
        toDate(measurement_start_time) AS date,
        test_name,
        probe_cc,
        quantile(.5)(JSONExtractFloat(scores, 'extra', 'test_runtime')) AS p50,
        quantile(.9)(JSONExtractFloat(scores, 'extra', 'test_runtime')) AS p90,
        count() as cnt
    FROM fastpath
    WHERE test_name IN ['torsf', 'tor', 'stunreachability', 'psiphon','riseupvpn']
    AND measurement_start_time > today() - interval 6 month
    AND measurement_start_time < today() - interval 1 day
    AND JSONHas(scores, 'extra', 'test_runtime')
    GROUP BY date, probe_cc, test_name
    """
    try:
        r = query_click(clickhouse, sql.text(q), {})
        return CircumventionRuntimeStatsResponse(results=pivot_circumvention_runtime_stats(r), v=0)

    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e), "v": 0})


DomainStr = Annotated[
    str,
    Field(
        strip_whitespace=True,
        pattern=r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[A-Za-z]{2,}$"
    )
]


class DomainMetadataResponse(BaseModel):
    canonical_domain: DomainStr = Field(..., description="Domain name")
    category_code: str = Field(..., description="Citizenlab Category Code")


@router.get("/domain_metadata", response_model=DomainMetadataResponse, tags=["private"])
def api_private_domain_metadata(
    clickhouse: ClickhouseDep,
    domain: DomainStr = Query(..., description="Domain Name"),
) -> DomainMetadataResponse:
    """Return the primary category code of a certain domain_name and its
    canonical representation.
    We consider the primary category code to be the category code of whatever is
    the shortest URL in the test lists giving higher priority to what is in the
    global list (e.g. if we have https://twitter.com/amnesty categorised as HUMR
    and https://twitter.com/ as GRP, we will be picking GRP as the canonical
    category code).
    The canonical representation of a domain is whatever is present in the
    global list. If it's not present, then the shortest possible
    representation in the other test lists.
    Some research related to this problem was done here:
    https://gist.github.com/hellais/fab319ae20b0ccca7b548a060ed66e14, where some
    notes were taken on what fixes need to be done in the test-lists to ensure
    all of this works as expected (ex. moving shortest URL representations from
    the country lists into the global list).
    """
    category_code = "MISC"

    if domain.startswith("www."):
        canonical_domain = domain[4:]
        domains = [canonical_domain, domain]
    else:
        canonical_domain = domain
        domains = [canonical_domain, "www." + domain]

    # case 1: domain with or without www is in the global list (cc = 'ZZ')
    q = """
        SELECT category_code, domain
        FROM citizenlab
        WHERE domain IN :domains
        AND cc = 'ZZ'
        ORDER BY length(url)
        LIMIT 1
    """
    res = query_click_one_row(clickhouse, sql.text(q), dict(domains=domains))
    if not res:
        # case 2: domain only inside a country list, so we just select the
        # shortest domain among the one with and without www
        q = """
            SELECT category_code, domain FROM citizenlab
            WHERE domain IN :domains
            ORDER BY length(url)
            LIMIT 1
        """
        res = query_click_one_row(clickhouse, sql.text(q), dict(domains=domains))

    if res:
        category_code = res["category_code"]
        canonical_domain = res["domain"]

    return DomainMetadataResponse(category_code=category_code, canonical_domain=canonical_domain)


class ASNMetadataResponse(BaseModel):
    org_name: str = Field("Unknown", description="ORG Name of ASN")


@router.get("/asnmeta", response_model=ASNMetadataResponse, tags=["private"])
def api_private_asnmeta(
    clickhouse: ClickhouseDep,
    asn: int = Query(..., description="Autonomous System Number, e.g. 1234"),
) -> ASNMetadataResponse:
    """Look up organization name by ASN"""

    q = """SELECT org_name
        FROM asnmeta
        WHERE asn = :asn
        ORDER BY changed DESC
        LIMIT 1
    """
    res = query_click_one_row(clickhouse, sql.text(q), dict(asn=asn))
    org_name = res["org_name"] if res else "Unknown"
    return ASNMetadataResponse(org_name=org_name)


class MeasuredNetworkStat(BaseModel):
    cnt: int = Field(..., description="Number of measurements")
    org_name: str = Field("", description="Organization name associated with the ASN")
    probe_asn: int = Field(..., description="ASN of network (int)")


class MeasuredNetworksResponse(BaseModel):
    results: List[MeasuredNetworkStat] = Field(..., description="Networks that have measurements")
    v: int = Field(..., description="Version of API response")


@router.get("/networks", response_model=MeasuredNetworksResponse, tags=["private"])
def api_private_networks(
    clickhouse: ClickhouseDep,
) -> MeasuredNetworksResponse:
    """List all networks that have measurements by per-ASN measurement count and associated organization name."""
    q = """
    SELECT probe_asn, cnt, org_name FROM (
        SELECT
        COUNT() as cnt,
        probe_asn
        FROM fastpath
        GROUP BY probe_asn
    ) as cnts

    LEFT JOIN (
        SELECT
        any(org_name) as org_name,
        asn
        FROM (
            SELECT org_name, asn
            FROM asnmeta
            ORDER BY changed DESC
        )
        GROUP BY asn
    ) as asorgs
    ON (asorgs.asn = cnts.probe_asn)
    """
    try:
        results = query_click(clickhouse, sql.text(q), {})
        return MeasuredNetworksResponse(results=results, v=0)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e), "v": 0})


class MeasuredDomainStat(BaseModel):
    category_code: str = Field(..., description="Citizenlab Category Code")
    domain_name: DomainStr = Field(..., description="Domain Name")
    measurement_count: int = Field(..., description="Number of measurements")


class DomainsMeasuredResponse(BaseModel):
    results: List[MeasuredDomainStat] = Field(..., description="Domains that have measurements")
    v: int = Field(..., description="Version of API response")


@router.get("/domains", response_model=DomainsMeasuredResponse, tags=["private"])
def api_private_domains(
    clickhouse: ClickhouseDep,
) -> DomainsMeasuredResponse:
    """List all the domains in the test-lists with their measurement count."""
    # The nested ORDER BY lower(cc) puts global entries (cc=ZZ) on top so that
    # any(category_code) picks it up as the most meaningful category code.
    q = """
    SELECT domain AS domain_name, category_code, measurement_count
    FROM (
        SELECT
        any(category_code) as category_code,
        domain FROM (
            SELECT domain, category_code
            FROM citizenlab
            ORDER BY lower(cc) != 'zz'
        )
        GROUP BY domain
    ) AS cz
    LEFT JOIN (
        SELECT domain, count() AS measurement_count
        FROM fastpath
        WHERE test_name = 'web_connectivity'
        GROUP BY domain
    ) AS fp
    ON (fp.domain == cz.domain)
    ORDER BY domain_name
    """
    try:
        results = query_click(clickhouse, sql.text(q), {})
        return DomainsMeasuredResponse(v=0, results=results)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e), "v": 0})
