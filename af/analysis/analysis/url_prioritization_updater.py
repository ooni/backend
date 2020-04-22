"""
Updates URL prioritization

Runs in a dedicated thread

Inputs:
    `citizenlab` db table
    country codes are in the `cc` column, lowercase, with the exception of ZZ

Outputs:
    web_connectivity target list JSON file
    fallback JSON file
"""

from typing import List
from pathlib import Path
import json
import logging
import random
import time

from psycopg2.extras import RealDictCursor
import psycopg2


from analysis.metrics import setup_metrics

log = logging.getLogger("analysis.upu")
metrics = setup_metrics(name="analysis.upu")


def connect_db(c):
    return psycopg2.connect(
        dbname=c["dbname"], user=c["dbuser"], host=c["dbhost"], password=c["dbpassword"]
    )


def algo_chao(s: List, k: int) -> List:
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


@metrics.timer("update_url_prioritization")
def _update_url_prioritization(conf):
    log.info("UPU: Started _update_url_prioritization")
    outdir = conf.output_directory / "url_prioritization"
    outdir.mkdir(parents=True, exist_ok=True)
    conn = connect_db(conf.standby)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    log.info("UPU: Regenerating URL prioritization file")
    sql = """SELECT priority, domain, url, cc, category_code FROM citizenlab"""
    cur.execute(sql)
    entries = list(cur.fetchall())
    conn.rollback()
    conn.close()

    entries_by_country = {}  # cc -> [entry, ... ]
    for e in entries:
        cc = e["cc"]
        if cc not in entries_by_country:
            entries_by_country[cc] = []
        entries_by_country[cc].append(e)

    del entries

    k = 10

    for cc, entry in entries_by_country.items():
        candidates = entries_by_country[cc] + entries_by_country["ZZ"]
        selected = algo_chao(candidates, k)

        test_items = []
        for entry in selected:
            cc = entry["cc"]
            test_items.append(
                {
                    "category_code": entry["category_code"],
                    "url": entry["url"],
                    "country_code": "XX" if cc == "ZZ" else cc,
                }
            )

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
        f = outdir / ("url_list.%s.json" % cc)
        tmpf = f.with_suffix(".tmp")
        j = json.dumps(out, sort_keys=True)
        tmpf.write_text(j)
        tmpf.rename(f)

    log.info("UPU: Done")


def url_prioritization_updater(conf):
    """Thread entry point
    """
    while True:
        try:
            _update_url_prioritization(conf)
        except Exception as e:
            log.exception(e)

        time.sleep(60 * 5)


# Manual run
def main():
    from argparse import Namespace

    logging.basicConfig(level=logging.DEBUG)
    c = Namespace(
        standby=dict(
            dbname="metadb", dbuser="readonly", dbhost="localhost", dbpassword=None
        ),
        output_directory=Path("prioritization_test")
    )
    _update_url_prioritization(c)


if __name__ == "__main__":
    main()
