"""
OONI Probe Services API - reactive URL prioritization

/api/v1/test-list/urls provides dynamic URL tests lists for web_connectivity
based on the citizenlab URL list and the measurements count from the last
7 days.

The ooni-update-counters service updates the counters_test_list table at intervals

The ooni-update-citizenlab service updates the citizenlab table at intervals

```
blockdiag {
  Probes [color = "#ffeeee"];
  "API: test-list/urls" [color = "#eeeeff"];
  Probes -> "API: receive msmt" -> "Fastpath" -> "DB: fastpath table";
  "DB: fastpath table" -> "ooni-update-counters service" -> "DB: counters_test_list table";
  "DB: counters_test_list table" -> "API: test-list/urls" -> Probes;
  "DB: citizenlab table" -> "API: test-list/urls";
}
```

"""

from collections import namedtuple
from typing import List, Dict
import random

from flask import Blueprint, current_app, request
from flask.json import jsonify
from sqlalchemy import sql as sa

from ooniapi.database import query_click, query_click_one_row
from ooniapi.config import metrics

prio_bp = Blueprint("prio", "probe_services_prio")


# # failover algorithm

CTZ = namedtuple("CTZ", ["url", "category_code"])
failover_test_items: Dict[str, List[CTZ]] = {}


def failover_fetch_citizenlab_data() -> Dict[str, List[CTZ]]:
    """Fetches the citizenlab table from the database.
    Used only once at startime for failover."""
    log = current_app.logger
    log.info("Started failover_fetch_citizenlab_data")
    sql = """SELECT category_code, url
    FROM citizenlab
    WHERE cc = 'ZZ'
    """
    out: Dict[str, List[CTZ]] = {}
    if current_app.config["USE_CLICKHOUSE"]:
        query = query_click(sql, {})
    else:
        query = current_app.db_session.execute(sql)  # pragma: no cover
    for e in query:
        catcode = e["category_code"]
        c = CTZ(e["url"], catcode)
        out.setdefault(catcode, []).append(c)

    log.info("Fetch done: %d" % len(out))
    return out


def failover_generate_test_list(country_code: str, category_codes: tuple, limit: int):
    global failover_test_items
    if not category_codes:
        category_codes = tuple(failover_test_items.keys())

    candidates: List[CTZ] = []
    for catcode in category_codes:
        if catcode not in failover_test_items:
            continue
        new = failover_test_items[catcode]
        candidates.extend(new)

    limit = min(limit, len(candidates))
    selected = random.sample(candidates, k=limit)
    out = [
        dict(category_code=entry.category_code, url=entry.url, country_code="XX")
        for entry in selected
    ]
    return out


# # reactive algorithm


def match_prio_rule(cz, pr: dict) -> bool:
    """Match a priority rule to citizenlab entry"""
    for k in ["category_code", "domain", "url"]:
        if pr[k] not in ("*", cz[k]):
            return False

    if cz["cc"] != "ZZ" and pr["cc"] not in ("*", cz["cc"]):
        return False

    return True


def compute_priorities(entries, prio_rules):
    # Order based on (msmt_cnt / priority) to provide balancing
    test_list = []
    for e in entries:
        # Calculate priority for an URL
        priority = 0
        for pr in prio_rules:
            if match_prio_rule(e, pr):
                priority += pr["priority"]

        o = dict(e)
        o["priority"] = priority
        o["weight"] = priority / max(e["msmt_cnt"], 0.1)
        test_list.append(o)

    return sorted(test_list, key=lambda k: k["weight"], reverse=True)


def fetch_reactive_url_list_pg(cc):  # pragma: no cover
    sql = """
SELECT category_code, domain, url, cc, COALESCE(msmt_cnt, 0)::float AS msmt_cnt
FROM (
    SELECT domain, url, cc, category_code
    FROM citizenlab
    WHERE
      citizenlab.cc = :cc_low
      OR citizenlab.cc = :cc
      OR citizenlab.cc = 'ZZ'
) AS citiz
LEFT OUTER JOIN (
    SELECT input, msmt_cnt
    FROM counters_test_list
    WHERE probe_cc = :cc
) AS cnt
ON (citiz.url = cnt.input)
"""
    # support uppercase or lowercase match
    q = current_app.db_session.execute(sql, dict(cc=cc, cc_low=cc.lower()))
    return tuple(q.fetchall())


def fetch_reactive_url_list_click(cc):
    q = """
SELECT category_code, domain, url, cc, COALESCE(msmt_cnt, 0) AS msmt_cnt
FROM (
    SELECT domain, url, cc, category_code
    FROM citizenlab
    WHERE
      citizenlab.cc = :cc_low
      OR citizenlab.cc = :cc
      OR citizenlab.cc = 'ZZ'
) AS citiz
LEFT OUTER JOIN (
    SELECT input, SUM(msmt_cnt) AS msmt_cnt
    FROM counters_asn_test_list
    WHERE probe_cc = :cc
    GROUP BY input
) AS cnt
ON (citiz.url = cnt.input)
"""
    # support uppercase or lowercase match
    q = query_click(sa.text(q), dict(cc=cc, cc_low=cc.lower()))
    return tuple(q)


@metrics.timer("fetch_reactive_url_list")
def fetch_reactive_url_list(cc: str):
    """Select all citizenlab URLs for the given probe_cc + ZZ
    Select measurements count from the last 7 days in a left outer join
    (without any info about priority)"""
    if current_app.config["USE_CLICKHOUSE"]:
        return fetch_reactive_url_list_click(cc)
    else:
        return fetch_reactive_url_list_pg(cc)


@metrics.timer("fetch_prioritization_rules")
def fetch_prioritization_rules(cc: str) -> tuple:
    sql = """SELECT category_code, cc, domain, url, priority
    FROM url_priorities WHERE cc = :cc OR cc = '*'
    """
    if current_app.config["USE_CLICKHOUSE"]:
        q = query_click(sa.text(sql), dict(cc=cc))
        return tuple(q)
    else:
        q = current_app.db_session.execute(sql, dict(cc=cc))  # pragma: no cover
        return tuple(q.fetchall())


@metrics.timer("generate_test_list")
def generate_test_list(
    country_code: str, category_codes: tuple, limit: int, debug: bool
):
    """Generate test list based on the amount of measurements in the last
    N days"""
    log = current_app.logger
    entries = fetch_reactive_url_list(country_code)
    log.info("fetched %d url entries", len(entries))
    prio_rules = fetch_prioritization_rules(country_code)
    log.info("fetched %d priority rules", len(prio_rules))
    li = compute_priorities(entries, prio_rules)
    # Filter unwanted category codes, replace ZZ, trim priority <= 0
    out = []
    for entry in li:
        if category_codes and entry["category_code"] not in category_codes:
            continue
        if entry["priority"] <= 0:
            continue

        cc = "XX" if entry["cc"] == "ZZ" else entry["cc"].upper()
        i = {
            "category_code": entry["category_code"],
            "url": entry["url"],
            "country_code": cc,
        }
        if debug:
            i["msmt_cnt"] = entry["msmt_cnt"]
            i["priority"] = entry["priority"]
            i["weight"] = entry["weight"]
        out.append(i)
        if len(out) >= limit:
            break

    return out


# # API entry point


@prio_bp.route("/api/v1/test-list/urls")
def list_test_urls():
    """Generate test URL list with prioritization
    https://orchestrate.ooni.io/api/v1/test-list/urls?country_code=IT
    ---
    produces:
      - application/json
    parameters:
      - name: country_code
        in: query
        type: string
        description: Two letter, uppercase country code
      - name: probe_cc
        in: query
        type: string
        description: Two letter, uppercase country code (alternative to country_code)
      - name: category_codes
        in: query
        type: string
        description: Comma separated list of URL categories, all uppercase
      - name: limit
        in: query
        type: integer
        description: Maximum number of URLs to return
      - name: debug
        in: query
        type: boolean
        description: Include measurement counts and priority
    responses:
      200:
        description: URL test list
        schema:
          type: object
          properties:
            metadata:
              type: object
              properties:
                count:
                  type: integer
            results:
              type: array
              items:
                type: object
                properties:
                  category_code:
                    type: string
                  country_code:
                    type: string
                  url:
                    type: string

    """
    global failover_test_items
    if failover_test_items == {}:  # initialize once
        failover_test_items = failover_fetch_citizenlab_data()

    log = current_app.logger
    param = request.args.get
    try:
        country_code = param("country_code") or param("probe_cc") or "ZZ"
        country_code = country_code.upper()
        category_codes = param("category_codes") or ""
        category_codes = set(c.strip().upper() for c in category_codes.split(","))
        category_codes.discard("")
        category_codes = tuple(category_codes)
        limit = int(param("limit") or -1)
        if limit == -1:
            limit = 9999
        debug = param("debug", "").lower() in ("true", "1", "yes")
    except Exception as e:
        log.error(e, exc_info=1)
        return jsonify({})

    try:
        test_items = generate_test_list(country_code, category_codes, limit, debug)
    except Exception as e:
        log.error(e, exc_info=1)
        # failover_generate_test_list runs without any database interaction
        test_items = failover_generate_test_list(country_code, category_codes, limit)

    # TODO: remove current_page / next_url / pages ?
    metrics.gauge("test-list-urls-count", len(test_items))
    out = {
        "metadata": {
            "count": len(test_items),
            "current_page": -1,
            "limit": -1,
            "next_url": "",
            "pages": 1,
        },
        "results": test_items,
    }
    return jsonify(out)
