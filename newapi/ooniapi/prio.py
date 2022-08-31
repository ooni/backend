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
from typing import List, Dict, Tuple
import random

from flask import Blueprint, current_app, request, Response, make_response
from flask.json import jsonify
from sqlalchemy import sql as sa

from ooniapi.database import query_click
from ooniapi.config import metrics
from ooniapi.measurements import param_asn, _convert_to_csv

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
    query = query_click(sql, {}, query_prio=7)
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
        if pr[k] not in ("", "*", cz[k]):
            return False

    if cz["cc"] != "ZZ" and pr["cc"] not in ("", "*", cz["cc"]):
        return False

    return True


def compute_priorities(entries: tuple, prio_rules: tuple) -> list:
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


@metrics.timer("fetch_reactive_url_list")
def fetch_reactive_url_list(cc: str, probe_asn: int) -> tuple:
    """Select all citizenlab URLs for the given probe_cc + ZZ
    Select measurements count from the current and previous week
    using a left outer join (without any info about priority)"""
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
    AND (week IN (toStartOfWeek(now()), toStartOfWeek(now() - interval 1 week)))
    --asn-filter--
    GROUP BY input
) AS cnt
ON (citiz.url = cnt.input)
"""
    if probe_asn != 0:
        q = q.replace("--asn-filter--", "AND probe_asn = :asn")

    # support uppercase or lowercase match
    r = query_click(sa.text(q), dict(cc=cc, cc_low=cc.lower(), asn=probe_asn), query_prio=7)
    return tuple(r)


@metrics.timer("fetch_prioritization_rules")
def fetch_prioritization_rules(cc: str) -> tuple:
    sql = """SELECT category_code, cc, domain, url, priority
    FROM url_priorities WHERE cc = :cc OR cc = '*' OR cc = ''
    """
    q = query_click(sa.text(sql), dict(cc=cc), query_prio=7)
    return tuple(q)


@metrics.timer("generate_test_list")
def generate_test_list(
    country_code: str, category_codes: tuple, probe_asn: int, limit: int, debug: bool
) -> Tuple[List, List, List]:
    """Generate test list based on the amount of measurements in the last
    N days"""
    log = current_app.logger
    entries = fetch_reactive_url_list(country_code, probe_asn)
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

    if debug:
        return out, entries, prio_rules
    return out, [], []


# # API entry points


@prio_bp.route("/api/v1/test-list/urls")
def list_test_urls() -> Response:
    """Generate test URL list with prioritization
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
        category_codes = param_category_codes()
        limit = int(param("limit") or -1)
        if limit == -1:
            limit = 9999
        debug = param("debug", "").lower() in ("true", "1", "yes")
    except Exception as e:
        log.error(e, exc_info=True)
        return jsonify({})

    try:
        test_items, _1, _2 = generate_test_list(
            country_code, category_codes, 0, limit, debug
        )
    except Exception as e:
        log.error(e, exc_info=True)
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


def param_category_codes() -> tuple:
    """Return a tuple of category codes without duplicates"""
    catcod = request.args.get("category_codes") or ""
    category_codes = set(c.strip().upper() for c in catcod.split(","))
    category_codes.discard("")
    return tuple(category_codes)


@prio_bp.route("/api/_/debug_prioritization")
def debug_prioritization() -> Response:
    """Generate prioritization debug data
    ---
    produces:
      - application/json
    parameters:
      - name: probe_cc
        in: query
        type: string
        description: Two letter, uppercase country code
      - name: category_codes
        in: query
        type: string
        description: Comma separated list of URL categories, all uppercase
      - name: probe_asn
        in: query
        type: string
        description: Probe ASN
      - name: limit
        in: query
        type: integer
        description: Maximum number of URLs to return
    responses:
      200:
        description: URL test list and debug data
        schema:
          type: object
    """
    param = request.args.get
    country_code = (param("probe_cc") or "ZZ").upper()
    category_codes = param_category_codes()
    asn = param_asn("probe_asn") or 0
    limit = int(param("limit") or -1)
    test_items, entries, prio_rules = generate_test_list(
        country_code, category_codes, asn, limit, True
    )
    return jsonify(dict(test_items=test_items, entries=entries, prio_rules=prio_rules))


@prio_bp.route("/api/_/show_countries_prioritization")
def show_countries_prioritization() -> Response:
    """Show computed priorities excluding global entries
    ---
    produces:
      - application/json
    parameters:
      - name: format
        in: query
        type: string
        description: |
          Output format, JSON (default) or CSV
        enum:
          - JSON
          - CSV
    responses:
      200:
        description: URL test list and debug data
        schema:
          type: object
    """
    sql = """SELECT domain, url, cc, category_code, 0 AS msmt_cnt
    FROM citizenlab WHERE cc != 'ZZ'
    """
    cz = tuple(query_click(sa.text(sql), {}))

    sql = "SELECT category_code, cc, domain, url, priority FROM url_priorities"
    prio_rules = tuple(query_click(sa.text(sql), {}))
    li = compute_priorities(cz, prio_rules)
    for x in li:
        x.pop("weight")
        x.pop("msmt_cnt")
        x["cc"] = x["cc"].upper()

    li = sorted(li, key=lambda x: (x["cc"], -x["priority"]))

    param = request.args.get
    resp_format = param("format", "JSON").upper()
    if resp_format == "CSV":
        csv_data = _convert_to_csv(li)
        response = make_response(csv_data)
        response.headers["Content-Type"] = "text/csv"
        return response

    return jsonify(li)
