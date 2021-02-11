"""
prefix: /api/_

In here live private API endpoints for use only by OONI services. You should
not rely on these as they are likely to change, break in unexpected ways. Also
there is no versioning on them.
"""
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

from urllib.parse import urljoin, urlencode

import math

from flask import Blueprint, current_app, request, abort
from flask.json import jsonify

from sqlalchemy import func, and_, or_, sql, select

from werkzeug.exceptions import BadRequest

from ooniapi.models import TEST_GROUPS, get_test_group_case
from ooniapi.countries import lookup_country
from ooniapi.utils import cachedjson

# The private API is exposed under the prefix /api/_
# e.g. https://api.ooni.io/api/_/test_names

api_private_blueprint = Blueprint("api_private", "measurements")

# TODO: configure tags for HTTP caching across where useful


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


@api_private_blueprint.route("/asn_by_month")
def api_private_asn_by_month():
    """Network count by month
    ---
    responses:
      '200':
        description: [{"date":"2018-08-31","value":4411}, ... ]
    """
    # OLAP-use-case
    cols = [sql.text("networks_by_month"), sql.text("month")]
    q = select(cols).select_from(sql.table("global_by_month"))
    q = current_app.db_session.execute(q)
    li = [dict(date=r[1], value=r[0]) for r in q]
    return cachedjson(24, li)


@api_private_blueprint.route("/countries_by_month")
def api_private_countries_by_month():
    """Countries count by month
    ---
    responses:
      '200':
        description: TODO
    """
    # OLAP-use-case
    cols = [sql.text("countries_by_month"), sql.text("month")]
    q = select(cols).select_from(sql.table("global_by_month"))
    q = current_app.db_session.execute(q)
    li = [dict(date=r[1], value=r[0]) for r in q]
    return cachedjson(24, li)


# FIXME UNUSED @api_private_blueprint.route("/runs_by_month")
# def api_private_runs_by_month():
#    """FIXME
#    ---
#    responses:
#      '200':
#        description: TODO
#    """
#    raise NotImplementedError
#    # The query takes ~6s on local SSD @ AMS on 2018-04-04.
#    # It was taking ~20s when it was fetching all the table from DB and doing grouping locally.
#    # TODO: use-count-table
#    # FIXME: support fastpath
#    now = datetime.now()
#    end_date = datetime(now.year, now.month, 1)
#    start_date = end_date - relativedelta(months=24)
#    rawsql = """SELECT
#        date_trunc('month', report.test_start_time) AS test_start_month,
#        count(*) AS count_1
#        FROM report
#        WHERE report.test_start_time >= :start_date
#        AND report.test_start_time < :end_date
#        GROUP BY test_start_month
#    """
#    params = dict(start_date=start_date, end_date=end_date)
#    q = current_app.db_session.execute(rawsql, params)
#    delta = relativedelta(months=+1, days=-1)
#    result = [
#        {"date": (bkt + delta).strftime("%Y-%m-%d"), "value": value}
#        for bkt, value in sorted(q.fetchall())
#    ]
#    return jsonify(result)
#
#
## FIXME UNUSED @api_private_blueprint.route("/reports_per_day")
# def api_private_reports_per_day():
#    """TODO
#    ---
#    responses:
#      '200':
#        description: TODO
#    """
#    # TODO: use-count-table
#    # FIXME: support fastpath
#    rawsql = """SELECT
#        count(date_trunc('day', report.test_start_time)) AS count_1,
#        date_trunc('day', report.test_start_time) AS date_trunc_2
#        FROM report
#        GROUP BY date_trunc('day', report.test_start_time)
#        ORDER BY date_trunc('day', report.test_start_time)
#    """
#    q = current_app.db_session.execute(rawsql)
#    result = [{"count": count, "date": date.strftime("%Y-%m-%d")} for count, date in q]
#    return jsonify(result)


@api_private_blueprint.route("/test_names", methods=["GET"])
def api_private_test_names():
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    TEST_NAMES = {
        "bridge_reachability": "Bridge Reachability",
        "dash": "DASH",
        "dns_consistency": "DNS Consistency",
        "facebook_messenger": "Facebook Messenger",
        "http_header_field_manipulation": "HTTP Header Field Manipulation",
        "http_host": "HTTP Host",
        "http_invalid_request_line": "HTTP Invalid Request Line",
        "http_requests": "HTTP Requests",
        "meek_fronted_requests_test": "Meek Fronted Requests",
        "multi_protocol_traceroute": "Multi Protocol Traceroute",
        "ndt": "NDT",
        "psiphon": "Psiphon",
        "tcp_connect": "TCP Connect",
        "telegram": "Telegram",
        "tor": "Tor",
        "vanilla_tor": "Vanilla Tor",
        "web_connectivity": "Web Connectivity",
        "whatsapp": "WhatsApp",
        "riseupvpn": "RiseupVPN",
        "dnscheck": "DNS Check",
        "urlgetter": "URL Getter",
    }
    test_names = [{"id": k, "name": v} for k, v in TEST_NAMES.items()]
    return cachedjson(1, test_names=test_names)


@api_private_blueprint.route("/countries", methods=["GET"])
def api_private_countries():
    """Summary of countries
    ---
    responses:
      '200':
        description: TODO
    """
    cols = [sql.text("measurement_count"), sql.text("probe_cc")]
    q = select(cols).select_from(sql.table("country_stats"))
    c = []
    for r in current_app.db_session.execute(q):
        try:
            name = lookup_country(r.probe_cc)
            c.append(dict(alpha_2=r.probe_cc, name=name, count=r.measurement_count))
        except KeyError:
            pass

    return cachedjson(24, countries=c)


@api_private_blueprint.route("/quotas_summary", methods=["GET"])
def api_private_quotas_summary():
    """Summary on rate-limiting quotas.
    [(first ipaddr octet, remaining daily quota), ... ]
    """
    return jsonify(current_app.limiter.get_lowest_daily_quotas_summary())


@api_private_blueprint.route("/check_report_id", methods=["GET"])
def check_report_id():
    """Check if a report_id exists in the fastpath table
    Used by https://github.com/ooni/probe/issues/1034
    ---
    parameters:
      - name: report_id
        in: query
        example: 20210208T162755Z_ndt_DZ_36947_n1_8swgXi7xNuRUyO9a
        type: string
        minLength: 10
        required: true
    responses:
      200:
        description: Check if a report_id exists in the fastpath table.
          Cached for a short time.
        schema:
          type: object
          properties:
            v:
              type: string
              description: version number of this response
            found:
              type: boolean
              description: True if found
            error:
              type: string
              description: error message
          example: { "found": true, "v": 0 }

    """
    report_id = request.args.get("report_id")
    s = sql.text("SELECT 1 FROM fastpath WHERE report_id = :rid LIMIT 1")
    try:
        q = current_app.db_session.execute(s, dict(rid=report_id))
        found = q.fetchone() is not None
        return cachedjson(2 / 60, v=0, found=found)  # cache for 2min

    except Exception as e:
        return cachedjson(0, v=0, error=str(e))


def last_30days():
    first_day = datetime.now() - timedelta(31)
    first_day = datetime(first_day.year, first_day.month, first_day.day)

    last_day = datetime.now() - timedelta(1)
    last_day = datetime(last_day.year, last_day.month, last_day.day)

    for d in daterange(first_day, last_day):
        yield d.strftime("%Y-%m-%d")


def get_recent_network_coverage(probe_cc, test_groups):
    where = [
        sql.text("measurement_start_day >= current_date - interval '31 day'"),
        sql.text("measurement_start_day < current_date"),
        sql.text("probe_cc = :probe_cc"),
    ]
    if test_groups is not None:
        tg_or = []
        for tg in test_groups:
            try:
                tg_names = TEST_GROUPS[tg]
                tg_or += [
                    sql.literal_column("test_name") == tg_name for tg_name in tg_names
                ]
            except KeyError:
                raise BadRequest("invalid test_group")
        where.append(or_(*tg_or))

    s = (
        select(
            [sql.text("COUNT(DISTINCT probe_asn)"), sql.text("measurement_start_day")]
        )
        .where(and_(*where))
        .group_by(sql.text("measurement_start_day"))
        .select_from(sql.table("counters_asn_noinput"))
    )

    network_map = {k: 0 for k in TEST_GROUPS.keys()}
    q = current_app.db_session.execute(s, {"probe_cc": probe_cc})
    for count, date in q:
        network_map[date.strftime("%Y-%m-%d")] = count

    network_coverage = []
    for test_day in last_30days():
        network_coverage.append(
            {"count": network_map.get(test_day, 0), "test_day": test_day}
        )
    return network_coverage


def get_recent_test_coverage(probe_cc):
    cols = [
        sql.text("SUM(measurement_count) AS count"),
        sql.text("measurement_start_day"),
        sql.text(get_test_group_case() + " AS test_group"),
    ]
    where = and_(
        sql.text("measurement_start_day >= (current_date - interval '31 day')"),
        # We exclude the last day to wait for the pipeline
        sql.text("measurement_start_day < current_date"),
        sql.text("probe_cc = :probe_cc"),
    )
    s = (
        select(cols)
        .where(where)
        .group_by(sql.text("test_group, measurement_start_day"))
        .order_by(sql.text("test_group, measurement_start_day"))
        .select_from(sql.table("counters_noinput"))
    )

    # Use a coverage_map table to fill in zeroes on missing days
    # TODO: cleanup/simplify
    q = current_app.db_session.execute(s, {"probe_cc": probe_cc})
    coverage_map = {k: {} for k in TEST_GROUPS.keys()}
    for count, measurement_start_day, test_group in q:
        ts = measurement_start_day.strftime("%Y-%m-%d")
        count = int(count)
        try:
            coverage_map[test_group][ts] = count
        except KeyError as e:
            # test_group='unknown' for missing test name in TEST_GROUPS
            log.error(e, exc_info=1)

    test_coverage = []
    for test_group, coverage in coverage_map.items():
        for measurement_start_day in last_30days():
            test_coverage.append(
                {
                    "count": coverage_map[test_group].get(measurement_start_day, 0),
                    "test_day": measurement_start_day,
                    "test_group": test_group,
                }
            )

    return test_coverage


@api_private_blueprint.route("/test_coverage", methods=["GET"])
def api_private_test_coverage():
    """Return number of measurements per day across test categories
    ---
    responses:
      '200':
          description: '{"network_coverage: [...], "test_coverage": [...]}'
    """
    # TODO: merge the two queries into one?
    # TODO: remove test categories or move aggregation to the front-end?
    # OLAP-use-case
    probe_cc = validate_probe_cc_query_param()
    test_groups = request.args.get("test_groups")
    if test_groups is not None:
        test_groups = test_groups.split(",")

    tc = get_recent_test_coverage(probe_cc)
    nc = get_recent_network_coverage(probe_cc, test_groups)
    return cachedjson(24, network_coverage=nc, test_coverage=tc)


@api_private_blueprint.route("/website_networks", methods=["GET"])
def api_private_website_network_tests():
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    probe_cc = validate_probe_cc_query_param()
    s = sql.text(
        """SELECT
        SUM(measurement_count) AS count,
        probe_asn
        FROM counters_asn_noinput
        WHERE
            measurement_start_day >= current_date - interval '31 day'
        AND measurement_start_day < current_date
        AND probe_cc = :probe_cc
        GROUP BY probe_asn
        ORDER BY count DESC
        """
    )
    q = current_app.db_session.execute(s, {"probe_cc": probe_cc})
    results = [dict(r) for r in q]
    return cachedjson(1, results=results)


@api_private_blueprint.route("/website_stats", methods=["GET"])
def api_private_website_stats():
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

    # disable bitmapscan otherwise PG uses the BRIN indexes instead of BTREE
    s = sql.text(
        """
        SET enable_bitmapscan = off;
        SELECT
             measurement_start_day,
             SUM(anomaly_count) as anomaly_count,
             SUM(confirmed_count) as confirmed_count,
             SUM(failure_count) as failure_count,
             SUM(measurement_count) as measurement_count
             FROM counters
             WHERE measurement_start_day >= current_date - interval '31 day'
             AND measurement_start_day < current_date
             AND probe_cc =  :probe_cc
             AND probe_asn = :probe_asn
             AND input = :input
             GROUP BY measurement_start_day
        """
    )
    q = current_app.db_session.execute(
        s, {"probe_cc": probe_cc, "probe_asn": probe_asn, "input": url}
    )
    results = [
        {
            "test_day": r.measurement_start_day,
            "anomaly_count": int(r.anomaly_count or 0),
            "confirmed_count": int(r.confirmed_count or 0),
            "failure_count": int(r.failure_count or 0),
            "total_count": int(r.measurement_count or 0),
        }
        for r in q
    ]
    return cachedjson(1, results=results)


@api_private_blueprint.route("/website_urls", methods=["GET"])
def api_private_website_test_urls():
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    limit = int(request.args.get("limit", 10))
    if limit <= 0:
        limit = 10
    offset = int(request.args.get("offset", 0))

    probe_cc = validate_probe_cc_query_param()
    probe_asn = validate_probe_asn_query_param()
    probe_asn = int(probe_asn.replace("AS", ""))

    # Count how many distinct inputs we have in this CC / ASN / period
    # disable bitmapscan otherwise PG uses the BRIN indexes instead of BTREE
    s = sql.text(
        """
        SET enable_bitmapscan = off;
        SELECT COUNT(DISTINCT(input)) as input_count
        FROM counters
        WHERE measurement_start_day >= CURRENT_DATE - interval '31 day'
        AND measurement_start_day < CURRENT_DATE
        AND test_name = 'web_connectivity'
        AND probe_cc = :probe_cc
        AND probe_asn = :probe_asn
    """
    )
    q = current_app.db_session.execute(s, dict(probe_cc=probe_cc, probe_asn=probe_asn))
    total_count = q.fetchone().input_count

    # Group msmts by CC / ASN / period  with LIMIT and OFFSET
    s = sql.text(
        """SELECT
        input,
        COALESCE(SUM(anomaly_count), 0) as anomaly_count,
        COALESCE(SUM(confirmed_count), 0) as confirmed_count,
        COALESCE(SUM(failure_count), 0) as failure_count,
        COALESCE(SUM(measurement_count), 0) as total_count
        FROM counters
        WHERE measurement_start_day >= current_date - interval '31 day'
        AND measurement_start_day < current_date
        AND test_name = 'web_connectivity'
        AND probe_cc =  :probe_cc
        AND probe_asn = :probe_asn
        GROUP BY input
        ORDER BY confirmed_count DESC, SUM(measurement_count) DESC,
                 anomaly_count DESC, input ASC
        LIMIT :limit
        OFFSET :offset
        """
    )
    q = current_app.db_session.execute(
        s,
        {
            "probe_cc": probe_cc,
            "probe_asn": probe_asn,
            "limit": limit,
            "offset": offset,
        },
    )
    results = [dict(r) for r in q]
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

    return cachedjson(1, metadata=metadata, results=results)  # TODO caching


@api_private_blueprint.route("/vanilla_tor_stats", methods=["GET"])
def api_private_vanilla_tor_stats():
    """Tor statistics over ASN for a given CC
    ---
    responses:
      '200':
        description: TODO
    """
    probe_cc = validate_probe_cc_query_param()

    s = sql.text(
        """SELECT
        SUM(failure_count) as failure_count,
        MAX(measurement_start_day) AS last_tested,
        probe_asn,
        SUM(anomaly_count) as anomaly_count,
        SUM(measurement_count) as total_count
        FROM counters_asn_noinput
        WHERE measurement_start_day > (current_date - interval '6 months')
        AND probe_cc =  :probe_cc
        GROUP BY probe_asn
    """
    )
    q = current_app.db_session.execute(s, {"probe_cc": probe_cc})

    nets = []
    blocked = 0
    for n in q:
        total_count = n.total_count or 0
        success_count = total_count - (n.anomaly_count or 0)
        nets.append(
            {
                "failure_count": n.failure_count or 0,
                "last_tested": n.last_tested,
                "probe_asn": n.probe_asn,
                "success_count": success_count,
                "test_runtime_avg": None,
                "test_runtime_max": None,
                "test_runtime_min": None,
                "total_count": total_count,
            }
        )
        if total_count > 5 and float(success_count) / float(total_count) < 0.6:
            blocked += 1

    lt = max(n["last_tested"] for n in nets)
    return cachedjson(0, networks=nets, notok_networks=blocked, last_tested=lt)


@api_private_blueprint.route("/im_networks", methods=["GET"])
def api_private_im_networks():
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    log = current_app.logger
    probe_cc = validate_probe_cc_query_param()
    test_names = [sql.literal_column("test_name") == t for t in TEST_GROUPS["im"]]
    s = (
        select(
            [
                sql.text("SUM(measurement_count) as msm_count"),
                sql.text("MAX(measurement_start_day) AS last_tested"),
                sql.text("probe_asn"),
                sql.text("test_name"),
            ]
        )
        .where(
            and_(
                sql.text("measurement_start_day >= current_date - interval '31 day'"),
                # We exclude the last day to wait for the pipeline
                sql.text("measurement_start_day < current_date"),
                sql.text("probe_cc = :probe_cc"),
                or_(*test_names),
            )
        )
        .group_by(sql.text("test_name, probe_asn"))
        .select_from(sql.table("counters_asn_noinput"))
        .order_by(sql.text("test_name, msm_count DESC"))
    )

    results = {}
    q = current_app.db_session.execute(s, {"probe_cc": probe_cc})
    for r in q:
        e = results.get(
            r.test_name,
            {"anomaly_networks": [], "ok_networks": [], "last_tested": r.last_tested},
        )
        e["ok_networks"].append(
            {
                "asn": r.probe_asn,
                "name": "",
                "total_count": r.msm_count,
                "last_tested": r.last_tested,
            }
        )
        if e["last_tested"] < r.last_tested:
            e["last_tested"] = r.last_tested
        results[r.test_name] = e

    return cachedjson(1, **results)  # TODO caching


def isomid(d) -> str:
    """Returns 2020-08-01T00:00:00+00:00"""
    return f"{d}T00:00:00+00:00"


@api_private_blueprint.route("/im_stats", methods=["GET"])
def api_private_im_stats():
    """TODO
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

    s = sql.text(
        """SELECT
        SUM(measurement_count) as total_count,
        measurement_start_day
        FROM counters_asn_noinput
        WHERE probe_cc = :probe_cc
        AND test_name = :test_name
        AND probe_asn = :probe_asn
        AND measurement_start_day >= current_date - interval '31 day'
        AND measurement_start_day < current_date
        GROUP BY measurement_start_day
        ORDER BY measurement_start_day
    """
    )

    query_params = {
        "probe_cc": probe_cc,
        "probe_asn": probe_asn,
        "test_name": test_name,
    }

    q = current_app.db_session.execute(s, query_params)

    tmp = {r.measurement_start_day: r for r in q}
    results = []
    days = [date.today() + timedelta(days=(d - 31)) for d in range(32)]
    for d in days:
        if d in tmp:
            e = {
                "test_day": isomid(tmp[d].measurement_start_day),
                "total_count": tmp[d].total_count,
            }
        else:
            e = {"test_day": isomid(d), "total_count": 0}

        e["anomaly_count"] = None
        results.append(e)

    return cachedjson(1, results=results)  # TODO caching


@api_private_blueprint.route("/network_stats", methods=["GET"])
def api_private_network_stats():
    """Network speed statistics - not implemented
    ---
    responses:
      '200':
        description: TODO
    """
    # TODO: implement the stats from NDT in fastpath and then here
    probe_cc = validate_probe_cc_query_param()

    return cachedjson(
        24,
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
def api_private_country_overview():
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
    # OLAP-use-case
    s = sql.text(
        """SELECT
        MIN(measurement_start_day) AS first_bucket_date,
        SUM(measurement_count) AS measurement_count,
        COUNT(DISTINCT probe_asn) AS network_count
        FROM counters_asn_noinput
        WHERE probe_cc = :probe_cc
    """
    )
    q = current_app.db_session.execute(s, {"probe_cc": probe_cc})
    r = q.fetchone()
    # NOTE: we are hardcoding a fixed first_bucket_date
    # FIXME: websites_confirmed_blocked
    return cachedjson(
        24,
        first_bucket_date=r.first_bucket_date,
        measurement_count=r.measurement_count,
        network_count=r.network_count,
    )


@api_private_blueprint.route("/global_overview", methods=["GET"])
def api_private_global_overview():
    """Provide global summary of measurements
    Sources: global_stats db table
    ---
    responses:
      '200':
        description: JSON struct TODO
    """
    # OLAP-use-case
    #  CREATE MATERIALIZED VIEW global_stats AS
    #  SELECT
    #      COUNT(DISTINCT probe_asn) AS network_count,
    #      COUNT(DISTINCT probe_cc) AS country_count,
    #      SUM(measurement_count) AS measurement_count
    #  FROM counters;
    q = select([sql.text("*")]).select_from(sql.table("global_stats"))
    r = current_app.db_session.execute(q).fetchone()
    return cachedjson(24, **dict(r))


@api_private_blueprint.route("/global_overview_by_month", methods=["GET"])
def api_private_global_by_month():
    """Provide global summary of measurements
    Sources: global_by_month db table
    ---
    responses:
      '200':
        description: JSON struct TODO
    """
    # OLAP-use-case
    q = select(
        [
            sql.text("countries_by_month"),
            sql.text("networks_by_month"),
            sql.text("measurements_by_month"),
            sql.text("month"),
        ]
    ).select_from(sql.table("global_by_month"))
    rows = current_app.db_session.execute(q).fetchall()
    n = [{"date": r[3], "value": r["networks_by_month"]} for r in rows]
    c = [{"date": r[3], "value": r["countries_by_month"]} for r in rows]
    m = [{"date": r[3], "value": r["measurements_by_month"]} for r in rows]
    return cachedjson(
        24, networks_by_month=n, countries_by_month=c, measurements_by_month=m
    )
