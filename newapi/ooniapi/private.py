"""
prefix: /api/_

In here live private API endpoints for use only by OONI services. You should
not rely on these as they are likely to change, break in unexpected ways. Also
there is no versioning on them.
"""
from datetime import date, datetime, timedelta
from itertools import product

from urllib.parse import urljoin, urlencode
from typing import Dict

import logging
import math

from flask import Blueprint, current_app, request, Response

from sqlalchemy import sql

from werkzeug.exceptions import BadRequest

from ooniapi.auth import role_required
from ooniapi.database import query_click, query_click_one_row
from ooniapi.models import TEST_GROUPS
from ooniapi.countries import lookup_country
from ooniapi.utils import cachedjson, nocachejson, jerror

# The private API is exposed under the prefix /api/_
# e.g. https://api.ooni.io/api/_/test_names

api_private_blueprint = Blueprint("api_private", "measurements")

# TODO: configure tags for HTTP caching across where useful

log = logging.getLogger()


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days)):
        yield start_date + timedelta(n)


def validate_probe_cc_query_param():
    probe_cc = request.args.get("probe_cc")
    if probe_cc is None or len(probe_cc) != 2:
        raise BadRequest("missing or incorrect probe_cc")
    return probe_cc


def validate_probe_asn_query_param():
    probe_asn = request.args.get("probe_asn")
    if probe_asn is None:
        # TODO: validate and return int?
        raise BadRequest("missing or incorrect probe_asn")
    return probe_asn


def expand_dates(li):
    """Replaces 'date' key in a list of dict"""
    for i in li:
        i["date"] = i["date"].strftime("%Y-%m-%dT00:00:00+00:00")


@api_private_blueprint.route("/asn_by_month")
def api_private_asn_by_month() -> Response:
    """Network count by month
    ---
    responses:
      '200':
        description: [{"date":"2018-08-31","value":4411}, ... ]
    """
    q = """SELECT
        COUNT(DISTINCT(probe_asn)) AS value,
        toStartOfMonth(measurement_start_time) AS date
    FROM fastpath
    WHERE measurement_start_time < toStartOfMonth(addMonths(now(), 1))
    AND measurement_start_time > toStartOfMonth(subtractMonths(now(), 24))
    ;
    GROUP BY date ORDER BY date
    """
    li = list(query_click(q, {}))
    expand_dates(li)
    return cachedjson("1d", li)


@api_private_blueprint.route("/countries_by_month")
def api_private_countries_by_month() -> Response:
    """Countries count by month
    ---
    responses:
      '200':
        description: TODO
    """
    q = """SELECT
        COUNT(DISTINCT(probe_cc)) AS value,
        toStartOfMonth(measurement_start_time) AS date
    FROM fastpath
    WHERE measurement_start_time < toStartOfMonth(addMonths(now(), 1))
    AND measurement_start_time > toStartOfMonth(subtractMonths(now(), 24))
    GROUP BY date ORDER BY date
    """
    li = list(query_click(q, {}))
    expand_dates(li)
    return cachedjson("1d", li)


@api_private_blueprint.route("/test_names", methods=["GET"])
def api_private_test_names() -> Response:
    """Provides test names and descriptions to Explorer
    ---
    responses:
      '200':
        description: TODO
    """
    # TODO: merge this and models.py:TEST_GROUPS
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
    test_names = [{"id": k, "name": v} for k, v in TEST_NAMES.items()]
    return cachedjson("1h", test_names=test_names)


@api_private_blueprint.route("/countries", methods=["GET"])
def api_private_countries() -> Response:
    """Summary of countries
    ---
    responses:
      '200':
        description: {"countries": [{"alpha_2": x, "count": y, "name":  z}, ... ]}
    """
    q = """
    SELECT probe_cc, COUNT() AS measurement_count
    FROM fastpath
    GROUP BY probe_cc ORDER BY probe_cc
    """
    c = []
    rows = query_click(q, {})
    for r in rows:
        try:
            name = lookup_country(r["probe_cc"])
            c.append(
                dict(alpha_2=r["probe_cc"], name=name, count=r["measurement_count"])
            )
        except KeyError:
            pass

    return cachedjson("1d", countries=c)


@api_private_blueprint.route("/quotas_summary", methods=["GET"])
@role_required(["admin"])
def api_private_quotas_summary() -> Response:
    """Summary on rate-limiting quotas.
    [(first ipaddr octet, remaining daily quota), ... ]
    """
    return nocachejson(current_app.limiter.get_lowest_daily_quotas_summary())


@api_private_blueprint.route("/check_report_id", methods=["GET"])
def check_report_id() -> Response:
    """Legacy. Used to check if a report_id existed in the fastpath table.
    Used by https://github.com/ooni/probe/issues/1034
    ---
    produces:
      - application/json
    parameters:
      - name: report_id
        in: query
        type: string
    responses:
      200:
        description: Always returns True.
        schema:
          type: object
          properties:
            v:
              type: integer
              description: version number of this response
            found:
              type: boolean
              description: True
          example: { "found": true, "v": 0 }

    """
    return cachedjson("1s", v=0, found=True)


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


def get_recent_test_coverage_ch(probe_cc):
    """Returns
    [{"count": 4888, "test_day": "2021-10-16", "test_group": "websites"}, ... ]
    """
    q = "SELECT DISTINCT(test_group) FROM test_groups ORDER BY test_group"
    rows = query_click(sql.text(q), {})
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
    rows = query_click(sql.text(q), dict(probe_cc=probe_cc))
    rows = tuple(rows)
    l30d = tuple(last_30days(32, 2))
    return pivot_test_coverage(rows, test_group_names, l30d)


def get_recent_network_coverage_ch(probe_cc, test_groups):
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

    return query_click(sql.text(s), d)


@api_private_blueprint.route("/test_coverage", methods=["GET"])
def api_private_test_coverage() -> Response:
    """Return number of measurements per day across test categories
    ---
    parameters:
      - name: probe_cc
        in: query
        type: string
        minLength: 2
        required: true
    responses:
      '200':
          description: '{"network_coverage: [...], "test_coverage": [...]}'
    """
    # TODO: merge the two queries into one?
    # TODO: remove test categories or move aggregation to the front-end?
    probe_cc = validate_probe_cc_query_param()
    test_groups = request.args.get("test_groups")
    if test_groups is not None:
        test_groups = test_groups.split(",")

    tc = get_recent_test_coverage_ch(probe_cc)
    nc = get_recent_network_coverage_ch(probe_cc, test_groups)
    return cachedjson("1h", network_coverage=nc, test_coverage=tc)


@api_private_blueprint.route("/website_networks", methods=["GET"])
def api_private_website_network_tests() -> Response:
    """TODO
    ---
    parameters:
      - name: probe_cc
        in: query
        type: string
        description: The two letter country code
    responses:
      '200':
        description: TODO
    """
    probe_cc = validate_probe_cc_query_param()
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
    results = query_click(sql.text(s), {"probe_cc": probe_cc})
    return cachedjson("0s", results=results)


@api_private_blueprint.route("/website_stats", methods=["GET"])
def api_private_website_stats() -> Response:
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    # uses_pg_index counters_day_cc_asn_input_idx a BRIN index was not used at
    # all, but BTREE on (measurement_start_day, probe_cc, probe_asn, input)
    # made queries go from full scan to 50ms
    url = request.args.get("input")
    probe_cc = validate_probe_cc_query_param()
    probe_asn = validate_probe_asn_query_param()

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
    results = query_click(sql.text(s), d)
    return cachedjson("0s", results=results)


@api_private_blueprint.route("/website_urls", methods=["GET"])
def api_private_website_test_urls() -> Response:
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    # TODO optimize or remove
    limit = int(request.args.get("limit", 10))
    if limit <= 0:
        limit = 10
    offset = int(request.args.get("offset", 0))

    probe_cc = validate_probe_cc_query_param()
    probe_asn = validate_probe_asn_query_param()
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
    q = query_click_one_row(sql.text(s), dict(probe_cc=probe_cc, probe_asn=probe_asn))
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
    results = query_click(sql.text(s), d)
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

    return cachedjson("1h", metadata=metadata, results=results)  # TODO caching


@api_private_blueprint.route("/vanilla_tor_stats", methods=["GET"])
def api_private_vanilla_tor_stats() -> Response:
    """Tor statistics over ASN for a given CC
    ---
    parameters:
      - name: probe_cc
        in: query
        type: string
        minLength: 2
        required: true
    responses:
      '200':
        description: TODO
    """
    probe_cc = validate_probe_cc_query_param()
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
    q = query_click(sql.text(s), {"probe_cc": probe_cc})
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
        return cachedjson("0s", networks=[], notok_networks=0, last_tested=None)

    lt = max(n["last_tested"] for n in nets)
    return cachedjson("0s", networks=nets, notok_networks=blocked, last_tested=lt)


@api_private_blueprint.route("/im_networks", methods=["GET"])
def api_private_im_networks() -> Response:
    """Instant messaging networks statistics
    ---
    responses:
      '200':
        description: TODO
    """
    probe_cc = validate_probe_cc_query_param()
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
    results: Dict[str, Dict] = {}
    test_names = sorted(TEST_GROUPS["im"])
    q = query_click(sql.text(s), {"probe_cc": probe_cc, "test_names": test_names})
    for r in q:
        e = results.get(
            r["test_name"],
            {
                "anomaly_networks": [],
                "ok_networks": [],
                "last_tested": r["last_tested"],
            },
        )
        e["ok_networks"].append(
            {
                "asn": r["probe_asn"],
                "name": "",
                "total_count": r["total_count"],
                "last_tested": r["last_tested"],
            }
        )
        if e["last_tested"] < r["last_tested"]:
            e["last_tested"] = r["last_tested"]
        results[r["test_name"]] = e

    return cachedjson("1h", **results)  # TODO caching


def isomid(d) -> str:
    """Returns 2020-08-01T00:00:00+00:00"""
    return f"{d}T00:00:00+00:00"


@api_private_blueprint.route("/im_stats", methods=["GET"])
def api_private_im_stats() -> Response:
    """Instant messaging statistics
    ---
    responses:
      '200':
        description: TODO
    """
    test_name = request.args.get("test_name")
    if not test_name or test_name not in TEST_GROUPS["im"]:
        raise BadRequest("invalid test_name")

    probe_cc = validate_probe_cc_query_param()
    probe_asn = validate_probe_asn_query_param()
    probe_asn = int(probe_asn.replace("AS", ""))

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
    q = query_click(sql.text(s), query_params)
    tmp = {r["test_day"]: r for r in q}
    results = []
    days = [date.today() + timedelta(days=(d - 31)) for d in range(32)]
    for d in days:
        if d in tmp:
            test_day = isomid(tmp[d]["test_day"])
            total_count = tmp[d]["total_count"]
        else:
            test_day = isomid(d)
            total_count = 0
        e = dict(anomaly_count=None, test_day=test_day, total_count=total_count)
        results.append(e)

    return cachedjson("1h", results=results)  # TODO caching


@api_private_blueprint.route("/network_stats", methods=["GET"])
def api_private_network_stats() -> Response:
    """Network speed statistics - not implemented
    ---
    parameters:
      - name: probe_cc
        in: query
        type: string
        description: The two letter country code
    responses:
      '200':
        description: TODO
    """
    # TODO: implement the stats from NDT in fastpath and then here
    probe_cc = validate_probe_cc_query_param()

    return cachedjson(
        "1d",
        {
            "metadata": {
                "current_page": 1,
                "limit": 10,
                "next_url": None,
                "offset": 0,
                "total_count": 0,
            },
            "results": [],
        },
    )

    # Sample:
    # {
    #     "metadata": {
    #         "current_page": 1,
    #         "limit": 10,
    #         "next_url": "https://api.ooni.io/api/_/network_stats?probe_cc=IT&offset=10&limit=10",
    #         "offset": 0,
    #         "total_count": 238,
    #     },
    #     "results": [
    #         {
    #             "asn": 3269,
    #             "asn_name": "ASN-IBSNAZ",
    #             "download_speed_mbps_median": 12.154,
    #             "middlebox_detected": null,
    #             "msm_count": 24596.0,
    #             "rtt_avg": 87.826,
    #             "upload_speed_mbps_median": 2.279,
    #         },
    #         ...
    #     ],
    # }


@api_private_blueprint.route("/country_overview", methods=["GET"])
def api_private_country_overview() -> Response:
    """Country-specific overview
    ---
    responses:
      '200':
        description: {
        "first_bucket_date":"2012-12-01",
        "measurement_count":6659891,
        "network_count":333}
    """
    # TODO: add circumvention_tools_blocked im_apps_blocked
    # middlebox_detected_networks websites_confirmed_blocked
    probe_cc = validate_probe_cc_query_param()
    s = """SELECT
        toDate(MIN(measurement_start_time)) AS first_bucket_date,
        COUNT() AS measurement_count,
        COUNT(DISTINCT probe_asn) AS network_count
        FROM fastpath
        WHERE probe_cc = :probe_cc
        AND measurement_start_time > '2012-12-01'
    """
    r = query_click_one_row(sql.text(s), {"probe_cc": probe_cc})
    assert r
    # FIXME: websites_confirmed_blocked
    return cachedjson("1d", **r)


@api_private_blueprint.route("/global_overview", methods=["GET"])
def api_private_global_overview() -> Response:
    """Provide global summary of measurements
    Sources: global_stats db table
    ---
    responses:
      '200':
        description: JSON struct TODO
    """
    q = """SELECT
        COUNT(DISTINCT(probe_asn)) AS network_count,
        COUNT(DISTINCT probe_cc) AS country_count,
        COUNT(*) AS measurement_count
    FROM fastpath
    """
    r = query_click_one_row(q, {})
    assert r
    return cachedjson("1d", **r)


@api_private_blueprint.route("/global_overview_by_month", methods=["GET"])
def api_private_global_by_month() -> Response:
    """Provide global summary of measurements
    Sources: global_by_month db table
    ---
    responses:
      '200':
        description: JSON struct TODO
    """
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
    rows = query_click(sql.text(q), {})
    rows = list(rows)

    n = [{"date": r["month"], "value": r["networks_by_month"]} for r in rows]
    c = [{"date": r["month"], "value": r["countries_by_month"]} for r in rows]
    m = [{"date": r["month"], "value": r["measurements_by_month"]} for r in rows]
    expand_dates(n)
    expand_dates(c)
    expand_dates(m)
    return cachedjson(
        "1d", networks_by_month=n, countries_by_month=c, measurements_by_month=m
    )


@api_private_blueprint.route("/circumvention_stats_by_country")
def api_private_circumvention_stats_by_country() -> Response:
    """Aggregated statistics on protocols used for circumvention,
    grouped by country.
    ---
    responses:
      200:
        description: List of dicts with keys probe_cc and cnt
    """
    q = """SELECT probe_cc, COUNT(*) as cnt
        FROM fastpath
        WHERE measurement_start_time > today() - interval 6 month
        AND measurement_start_time < today() - interval 1 day
        AND test_name IN ['torsf', 'tor', 'stunreachability', 'psiphon','riseupvpn']
        GROUP BY probe_cc ORDER BY probe_cc
    """
    try:
        result = query_click(sql.text(q), {})
        return cachedjson("1d", v=0, results=result)

    except Exception as e:
        return cachedjson("0d", v=0, error=str(e))


def pivot_circumvention_runtime_stats(rows):
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
        dict(
            test_name=k[0],
            probe_cc=k[1],
            date=k[2],
            v=tmp.get(k, no_data),
        )
        for k in product(test_names, ccs, dates)
    ]
    return result


@api_private_blueprint.route("/circumvention_runtime_stats")
def api_private_circumvention_runtime_stats() -> Response:
    """Runtime statistics on protocols used for circumvention,
    grouped by date, country, test_name.
    ---
    responses:
      200:
        description: List of dicts with keys probe_cc and cnt
    """
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
        r = query_click(sql.text(q), {})
        result = pivot_circumvention_runtime_stats(r)
        return cachedjson("1d", v=0, results=result)

    except Exception as e:
        return jerror(str(e), v=0)


@api_private_blueprint.route("/domain_metadata")
def api_private_domain_metadata() -> Response:
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

    Returns:
    {
        "category_code": "CITIZENLAB_CATEGORY_CODE",
        "canonical_domain": "canonical.tld"
    }
    """
    category_code = "MISC"
    domain = request.args.get("domain")
    if domain is None:
        raise BadRequest("missing domain")

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
    res = query_click_one_row(sql.text(q), dict(domains=domains))
    if not res:
        # case 2: domain only inside a country list, so we just select the
        # shortest domain among the one with and without www
        q = """
            SELECT category_code, domain FROM citizenlab
            WHERE domain IN :domains
            ORDER BY length(url)
            LIMIT 1
        """
        res = query_click_one_row(sql.text(q), dict(domains=domains))

    if res:
        category_code = res["category_code"]
        canonical_domain = res["domain"]

    j = dict(category_code=category_code, canonical_domain=canonical_domain)
    return cachedjson("2h", **j)
