
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
from typing import List, Tuple
import logging

from .common.clickhouse_utils import query_click

from clickhouse_driver import Client as Clickhouse
import sqlalchemy as sa

log = logging.getLogger(__name__)

## Reactive algorithm

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

def fetch_reactive_url_list(
    clickhouse_db: Clickhouse, cc: str, probe_asn: int
) -> tuple:
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
    r = query_click(
        clickhouse_db,
        sa.text(q),
        dict(cc=cc, cc_low=cc.lower(), asn=probe_asn),
        query_prio=1,
    )
    return tuple(r)

# TODO(luis) add timing
def fetch_prioritization_rules(clickhouse_db: Clickhouse, cc: str) -> tuple:
    sql = """SELECT category_code, cc, domain, url, priority
    FROM url_priorities WHERE cc = :cc OR cc = '*' OR cc = ''
    """
    q = query_click(clickhouse_db, sa.text(sql), dict(cc=cc), query_prio=1)
    return tuple(q)

# TODO(luis) add timing 
def generate_test_list(
    clickhouse: Clickhouse,
    country_code: str,
    category_codes: List,
    probe_asn: int,
    limit: int,
    debug: bool,
) -> Tuple[List, Tuple, Tuple]:
    """Generate test list based on the amount of measurements in the last
    N days"""
    entries = fetch_reactive_url_list(clickhouse, country_code, probe_asn)
    log.info("fetched %d url entries", len(entries))
    prio_rules = fetch_prioritization_rules(clickhouse, country_code)
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
    return out, (), ()