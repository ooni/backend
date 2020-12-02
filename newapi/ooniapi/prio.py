"""
OONI Probe Services API - URL prioritization
"""

from typing import List
import random
import time

from flask import Blueprint, current_app, request
from flask.json import jsonify

prio_bp = Blueprint("prio", "probe_services_prio")

# TODO  add unit tests

test_items = {}
last_update_time = 0


def update_url_prioritization():
    log = current_app.logger
    log.info("Started update_url_prioritization")
    # conn = connect_db(conf)
    # cur = conn.cursor(cursor_factory=RealDictCursor)

    log.info("Regenerating URL prioritization file")
    sql = """SELECT priority, domain, url, cc, category_code FROM citizenlab"""
    q = current_app.db_session.execute(sql)
    entries = list(q.fetchall())

    # Create dict: cc -> category_code -> [entry, ... ]
    entries_by_country = {}
    for e in entries:
        country = e["cc"].upper()
        if country not in entries_by_country:
            entries_by_country[country] = {}
        ccode = e["category_code"]
        entries_by_country[country].setdefault(ccode, []).append(e)

    # Merge ZZ into each country, so that "global" urls are given out to probes
    # from every country. Also keep ZZ as valid cc in case a probe requests it
    zz = entries_by_country["ZZ"]
    for ccode, country_dict in entries_by_country.items():
        for category_code, prio_test_items in zz.items():
            country_dict.setdefault(category_code, []).extend(prio_test_items)

    log.info("Update done: %d" % len(entries_by_country))
    return entries_by_country


def algo_chao(s: List, k: int) -> List:
    """Chao weighted random sampling
    """
    n = len(s)
    assert len(s) >= k
    wsum = 0
    r = s[:k]
    assert len(r) == k
    for i in range(0, n):
        wsum = wsum + s[i]["priority"]
        if i < k:
            continue
        p = s[i]["priority"] / wsum  # probability for this item
        j = random.random()
        if j <= p:
            pos = random.randint(0, k - 1)
            r[pos] = s[i]

    return r


def generate_test_list(country_code: str, category_codes: str, limit: int):
    global test_items, last_update_time
    log = current_app.logger

    if last_update_time < time.time() - 600:  # conf.refresh_interval:
        last_update_time = time.time()
        try:
            test_items = update_url_prioritization()
        except Exception as e:
            log.error(e, exc_info=1)

    candidates_d = test_items[country_code]  # category_code -> [test_item, ... ]

    if category_codes:
        category_codes = [c.strip().upper() for c in category_codes.split(",")]
    else:
        category_codes = candidates_d.keys()

    candidates = []
    for ccode in category_codes:
        s = candidates_d.get(ccode, [])
        candidates.extend(s)

    log.info("%d candidates", len(candidates))

    if limit == -1:
        limit = 100
    limit = min(limit, len(candidates))
    selected = algo_chao(candidates, limit)

    out = []
    for entry in selected:
        cc = "XX" if entry["cc"] == "ZZ" else entry["cc"].upper()
        out.append(
            {
                "category_code": entry["category_code"],
                "url": entry["url"],
                "country_code": cc,
            }
        )
    return out


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
      - name: category_code
        in: query
        type: string
        description: Comma separated list of URL categories, all uppercase
    responses:
      '200':
        description: URL test list
    """
    log = current_app.logger
    param = request.args.get
    try:
        country_code = (param("country_code") or "ZZ").upper()
        category_codes = param("category_code")
        limit = int(param("limit") or -1)
        test_items = generate_test_list(country_code, category_codes, limit)
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
    except Exception as e:
        log.error(e, exc_info=1)
        return jsonify({})
