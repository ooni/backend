"""
prefix: /api/_

In here live private API endpoints for use only by OONI services. You should
not rely on these as they are likely to change, break in unexpected ways. Also
there is no versioning on them.
"""
from datetime import date, datetime, timedelta

from urllib.parse import urljoin, urlencode

import logging
import math

from flask import Blueprint, current_app, request
from flask.json import jsonify

from sqlalchemy import and_, or_, sql, select

from werkzeug.exceptions import BadRequest

from ooniapi.database import query_click, query_click_one_row
from ooniapi.models import TEST_GROUPS, get_test_group_case
from ooniapi.countries import lookup_country
from ooniapi.utils import cachedjson

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


@api_private_blueprint.route("/asn_by_month")
def api_private_asn_by_month():
    """Network count by month
    ---
    responses:
      '200':
        description: [{"date":"2018-08-31","value":4411}, ... ]
    """
    if current_app.config["USE_CLICKHOUSE"]:
        q = """SELECT
            COUNT(DISTINCT(probe_asn)) AS value,
            toStartOfMonth(measurement_start_time) AS date
        FROM fastpath
        WHERE measurement_start_time < toStartOfMonth(addMonths(now(), 1))
        AND measurement_start_time > toStartOfMonth(subtractMonths(now(), 25))
        GROUP BY date ORDER BY date
        """
        li = list(query_click(q, {}))
    else:  # pragma: no cover
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
    if current_app.config["USE_CLICKHOUSE"]:
        q = """SELECT
            COUNT(DISTINCT(probe_cc)) AS value,
            toStartOfMonth(measurement_start_time) AS date
        FROM fastpath
        WHERE measurement_start_time < toStartOfMonth(addMonths(now(), 1))
        AND measurement_start_time > toStartOfMonth(subtractMonths(now(), 25))
        GROUP BY date ORDER BY date
        """
        li = list(query_click(q, {}))
    else:  # pragma: no cover
        cols = [sql.text("countries_by_month"), sql.text("month")]
        q = select(cols).select_from(sql.table("global_by_month"))
        q = current_app.db_session.execute(q)
        li = [dict(date=r[1], value=r[0]) for r in q]
    return cachedjson(24, li)


@api_private_blueprint.route("/test_names", methods=["GET"])
def api_private_test_names():
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
    return cachedjson(1, test_names=test_names)


@api_private_blueprint.route("/countries", methods=["GET"])
def api_private_countries():
    """Summary of countries
    ---
    responses:
      '200':
        description: {"countries": [{"alpha_2": x, "count": y, "name":  z}, ... ]}
    """
    if current_app.config["USE_CLICKHOUSE"]:
        q = """
        SELECT probe_cc, COUNT() AS measurement_count
        FROM fastpath
        GROUP BY probe_cc ORDER BY probe_cc
        """
        c = []
        q = query_click(q, {})
        for r in q:
            try:
                name = lookup_country(r["probe_cc"])
                c.append(
                    dict(alpha_2=r["probe_cc"], name=name, count=r["measurement_count"])
                )
            except KeyError:
                pass
    else:  # pragma: no cover
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
    produces:
      - application/json
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
              type: integer
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
        if current_app.config["USE_CLICKHOUSE"]:
            q = query_click_one_row(s, dict(rid=report_id))
            found = q is not None

        else:
            q = current_app.db_session.execute(s, dict(rid=report_id))
            found = q.fetchone() is not None
        return cachedjson(2 / 60, v=0, found=found)  # cache for 2min

    except Exception as e:
        return cachedjson(0, v=0, error=str(e))


def last_30days(begin=31, end=1):
    first_day = datetime.now() - timedelta(begin)
    first_day = datetime(first_day.year, first_day.month, first_day.day)

    last_day = datetime.now() - timedelta(end)
    last_day = datetime(last_day.year, last_day.month, last_day.day)

    for d in daterange(first_day, last_day):
        yield d.strftime("%Y-%m-%d")


def get_recent_network_coverage_pg(probe_cc, test_groups):  # pragma: no cover
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


def get_recent_test_coverage_pg(probe_cc):  # pragma: no cover
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
    WHERE test_day >= today() - interval 32 day
        AND test_day < today() - interval 2 day
        AND probe_cc = :probe_cc
        --mark--
    GROUP BY test_day ORDER BY test_day
    WITH FILL
        FROM today() - interval 31 day
        TO today() - interval 2 day
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

    q = query_click(sql.text(s), d)
    return list(q)


@api_private_blueprint.route("/test_coverage", methods=["GET"])
def api_private_test_coverage():
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

    if current_app.config["USE_CLICKHOUSE"]:
        tc = get_recent_test_coverage_ch(probe_cc)
        nc = get_recent_network_coverage_ch(probe_cc, test_groups)
    else:  # pragma: no cover
        tc = get_recent_test_coverage_pg(probe_cc)
        nc = get_recent_network_coverage_pg(probe_cc, test_groups)
    # FIXME
    return cachedjson(0, network_coverage=nc, test_coverage=tc)


@api_private_blueprint.route("/website_networks", methods=["GET"])
def api_private_website_network_tests():
    """TODO
    ---
    responses:
      '200':
        description: TODO
    """
    probe_cc = validate_probe_cc_query_param()
    if current_app.config["USE_CLICKHOUSE"]:
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
        q = query_click(sql.text(s), {"probe_cc": probe_cc})
        results = list(q)
    else:  # pragma: no cover
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

    if current_app.config["USE_CLICKHOUSE"]:
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
        q = query_click(sql.text(s), d)
        results = list(q)
    else:  # pragma: no cover
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

    if current_app.config["USE_CLICKHOUSE"]:
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
        q = query_click_one_row(
            sql.text(s), dict(probe_cc=probe_cc, probe_asn=probe_asn)
        )
        total_count = q["input_count"]
    else:  # pragma: no cover
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
        q = current_app.db_session.execute(
            s, dict(probe_cc=probe_cc, probe_asn=probe_asn)
        )
        total_count = q.fetchone().input_count

    # Group msmts by CC / ASN / period with LIMIT and OFFSET
    if current_app.config["USE_CLICKHOUSE"]:
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
        q = query_click(sql.text(s), d)
        results = list(q)
    else:  # pragma: no cover
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
    if current_app.config["USE_CLICKHOUSE"]:
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

    else:  # pragma: no cover
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
    """Instant messaging networks statistics
    ---
    responses:
      '200':
        description: TODO
    """
    log = current_app.logger
    probe_cc = validate_probe_cc_query_param()
    if current_app.config["USE_CLICKHOUSE"]:
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
        results = {}
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

    else:  # pragma: no cover
        test_names = [sql.column("test_name") == t for t in TEST_GROUPS["im"]]
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
                    sql.text(
                        "measurement_start_day >= current_date - interval '31 day'"
                    ),
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
                {
                    "anomaly_networks": [],
                    "ok_networks": [],
                    "last_tested": r.last_tested,
                },
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

    if current_app.config["USE_CLICKHOUSE"]:
        s = """SELECT
            COUNT() as total_count,
            toDate(measurement_start_time) as test_day
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

    else:  # pragma: no cover
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
    if current_app.config["USE_CLICKHOUSE"]:
        s = """SELECT
            toDate(MIN(measurement_start_time)) AS first_bucket_date,
            COUNT() AS measurement_count,
            COUNT(DISTINCT probe_asn) AS network_count
            FROM fastpath
            WHERE probe_cc = :probe_cc
        """
        r = query_click_one_row(sql.text(s), {"probe_cc": probe_cc})
    else:  # pragma: no cover
        s = sql.text(
            """SELECT
            MIN(measurement_start_day) AS first_bucket_date,
            SUM(measurement_count) AS measurement_count,
            COUNT(DISTINCT probe_asn) AS network_count
            FROM counters_asn_noinput
            WHERE probe_cc = :probe_cc
        """
        )
        # NOTE: we are hardcoding a fixed first_bucket_date
        q = current_app.db_session.execute(s, {"probe_cc": probe_cc})
        r = q.fetchone()
        r = dict(
            first_bucket_date=r.first_bucket_date,
            measurement_count=r.measurement_count,
            network_count=r.network_count,
        )
    # FIXME: websites_confirmed_blocked
    return cachedjson(24, **r)


@api_private_blueprint.route("/global_overview", methods=["GET"])
def api_private_global_overview():
    """Provide global summary of measurements
    Sources: global_stats db table
    ---
    responses:
      '200':
        description: JSON struct TODO
    """
    if current_app.config["USE_CLICKHOUSE"]:
        q = """SELECT
            COUNT(DISTINCT(probe_asn)) AS network_count,
            COUNT(DISTINCT probe_cc) AS country_count,
            COUNT(*) AS measurement_count
        FROM fastpath
        """
        r = query_click_one_row(q, {})
        return cachedjson(24, **r)

    else:  # pragma: no cover
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
    if current_app.config["USE_CLICKHOUSE"]:
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

    else:  # pragma: no cover
        q = select(
            [
                sql.text("countries_by_month"),
                sql.text("networks_by_month"),
                sql.text("measurements_by_month"),
                sql.text("month"),
            ]
        ).select_from(sql.table("global_by_month"))
        rows = current_app.db_session.execute(q).fetchall()

    n = [{"date": r["month"], "value": r["networks_by_month"]} for r in rows]
    c = [{"date": r["month"], "value": r["countries_by_month"]} for r in rows]
    m = [{"date": r["month"], "value": r["measurements_by_month"]} for r in rows]
    return cachedjson(
        24, networks_by_month=n, countries_by_month=c, measurements_by_month=m
    )


@api_private_blueprint.route("/circumvention_stats_by_country")
def api_private_circumvention_stats_by_country():
    """Aggregated statistics on protocols used for circumvention,
    grouped by country.
    ---
    responses:
      200:
        description: List of dicts with keys probe_cc and cnt
    """
    if not current_app.config["USE_CLICKHOUSE"]:
        return jsonify({"v": 0, "error": "Not supported"})

    q = """SELECT probe_cc, COUNT(*) as cnt
        FROM fastpath
        WHERE measurement_start_time > today() - interval 6 month
        AND measurement_start_time < today() - interval 1 day
        AND test_name IN ['torsf', 'tor', 'stunreachability', 'psiphon','riseupvpn']
        GROUP BY probe_cc ORDER BY probe_cc
    """
    try:
        q = query_click(sql.text(q), {})
        result = [dict(x) for x in q]
        return cachedjson(24, v=0, results=result)

    except Exception as e:
        return jsonify({"v": 0, "error": str(e)})
