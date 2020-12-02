"""
OONI Probe Services API - reactive URL prioritization

/api/v1/test-list/urls provides dynamic URL tests lists for web_connectivity
based on the citizenlab URL list and the measurements count from the last
7 days.

The ooni-update-counters service updates the counters table at intervals

The ooni-update-citizenlab service updates the citizenlab table at intervals

```
blockdiag {
  Probes [color = "#ffeeee"];
  "API: test-list/urls" [color = "#eeeeff"];
  Probes -> "API: receive msmt" -> "Fastpath" -> "DB: fastpath table";
  "DB: fastpath table" -> "ooni-update-counters service" -> "DB: counters table";
  "DB: counters table" -> "API: test-list/urls" -> Probes;
  "DB: citizenlab table" -> "API: test-list/urls";
}
```

"""

from collections import namedtuple
from typing import List, Dict
import random
import time

from flask import Blueprint, current_app, request
from flask.json import jsonify

from ooniapi.config import metrics

prio_bp = Blueprint("prio", "probe_services_prio")


# # failover algorithm

CTZ = namedtuple("CTZ", ["priority", "url", "category_code"])
failover_test_items: Dict[str, List[CTZ]] = {}


@metrics.timer("fetch_citizenlab_data")
def fetch_citizenlab_data() -> Dict[str, List[CTZ]]:
    """Fetch the citizenlab table from the database"""
    log = current_app.logger
    log.info("Started fetch_citizenlab_data")
    sql = """SELECT category_code, priority, url
    FROM citizenlab
    WHERE cc = 'ZZ'
    """
    out: Dict[str, List[CTZ]] = {}
    query = current_app.db_session.execute(sql)
    for e in query:
        catcode = e["category_code"]
        c = CTZ(e["priority"], e["url"], catcode)
        out.setdefault(catcode, []).append(c)

    log.info("Fetch done: %d" % len(out))
    return out


def algo_chao(s: List, k: int) -> List:
    """Chao weighted random sampling"""
    n = len(s)
    assert len(s) >= k
    wsum = 0
    r = s[:k]
    assert len(r) == k
    for i in range(0, n):
        wsum = wsum + s[i].priority
        if i < k:
            continue
        p = s[i].priority / wsum  # probability for this item
        j = random.random()
        if j <= p:
            pos = random.randint(0, k - 1)
            r[pos] = s[i]

    return r


def failover_generate_test_list(country_code: str, category_codes: tuple, limit: int):
    global failover_test_items
    if not category_codes:
        category_codes = tuple(failover_test_items.keys())

    log = current_app.logger
    candidates: List[CTZ] = []
    for catcode in category_codes:
        if catcode not in failover_test_items:
            continue
        new = failover_test_items[catcode]
        candidates.extend(new)

    limit = min(limit, len(candidates))
    selected = algo_chao(candidates, limit)
    out = [
        dict(category_code=entry.category_code, url=entry.url, country_code="XX")
        for entry in selected
    ]
    return out


# # reactive algorithm


@metrics.timer("fetch_reactive_url_list")
def fetch_reactive_url_list(cc: str):
    """Fetch test URL from the citizenlab table in the database
    weighted by the amount of measurements in the last N days
    """
    log = current_app.logger
    log.info("Started fetch_reactive_url_list")

    # Select all citizenlab URLs for the given probe_cc + ZZ
    # Select measurements count from the last 7 days in a left outer join
    # Order based on msmt_cnt / priority to provide balancing
    # When the msmt_cnt / priority ratio is the same, also use RANDOM() to
    # shuffle. GREATEST(...) prevents division by zero.
    sql = """
SELECT category_code, url, cc
FROM (
    SELECT priority, url, cc, category_code
    FROM citizenlab
    WHERE
      UPPER(citizenlab.cc) = :cc
      OR citizenlab.cc = 'ZZ'
) AS citiz
LEFT OUTER JOIN (
    SELECT input, SUM(measurement_count) AS msmt_cnt
    FROM counters
    WHERE
        measurement_start_day < CURRENT_DATE + interval '1 days'
        AND measurement_start_day > CURRENT_DATE - interval '8 days'
        AND probe_cc = :cc
        AND test_name = 'web_connectivity'
    GROUP BY input
) AS cnt
ON (citiz.url = cnt.input)
ORDER BY COALESCE(msmt_cnt, 0)::float / GREATEST(priority, 1), RANDOM()
"""
    q = current_app.db_session.execute(sql, dict(cc=cc))
    entries = tuple(q.fetchall())
    log.info("%d entries", len(entries))
    return entries


@metrics.timer("generate_test_list")
def generate_test_list(country_code: str, category_codes: tuple, limit: int):
    """Generate test list based on the amount of measurements in the last N days
    """
    log = current_app.logger
    out = []
    li = fetch_reactive_url_list(country_code)
    for entry in li:
        if category_codes and entry["category_code"] not in category_codes:
            continue

        cc = "XX" if entry["cc"] == "ZZ" else entry["cc"].upper()
        out.append(
            {
                "category_code": entry["category_code"],
                "url": entry["url"],
                "country_code": cc,
            }
        )
        if len(out) >= limit:
            break

    return out


# # API entry point


@prio_bp.route("/api/v1/test-list/urls")
def list_test_urls():
    """Generate test URL list with prioritization
    https://orchestrate.ooni.io/api/v1/test-list/urls?country_code=IT
    ---
    parameters:
      - name: country_code
        in: query
        type: string
        description: Two letter, uppercase country code
      - name: category_codes
        in: query
        type: string
        description: Comma separated list of URL categories, all uppercase
    responses:
      '200':
        description: URL test list
    """
    global failover_test_items
    if failover_test_items == {}:  # initialize once
        failover_test_items = fetch_citizenlab_data()

    log = current_app.logger
    param = request.args.get
    try:
        country_code = (param("country_code") or "ZZ").upper()
        category_codes = param("category_codes") or ""
        category_codes = set(c.strip().upper() for c in category_codes.split(","))
        category_codes.discard("")
        category_codes = tuple(category_codes)
        limit = int(param("limit") or -1)
        if limit == -1:
            limit = 100
    except Exception as e:
        log.error(e, exc_info=1)
        return jsonify({})

    try:
        test_items = generate_test_list(country_code, category_codes, limit)
    except Exception as e:
        log.error(e, exc_info=1)
        # failover_generate_test_list runs without any database interaction
        test_items = failover_generate_test_list(country_code, category_codes, limit)

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
