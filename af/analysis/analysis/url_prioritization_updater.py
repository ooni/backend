"""
Updates URL prioritization

Inputs:
    `citizenlab` and `url_priorities` db tables
    country codes are in the `cc` column, lowercase, with the exception of ZZ

"""

import logging
from typing import List, Dict

from psycopg2.extras import RealDictCursor

from analysis.metrics import setup_metrics

log = logging.getLogger("analysis.prio_up")
metrics = setup_metrics(name="analysis.prio_up")


def queryall(cur, sql: str) -> list:
    log.debug(f"Running {sql}")
    cur.execute(sql)
    return cur.fetchall()


def match_prio_rule(cz, pr: dict) -> bool:
    """Match a priority rule to citizenlab entry"""
    for k in ["category_code", "cc", "domain", "url"]:
        if pr[k] not in ("*", cz[k]):
            return False

    return True


def compute_url_priorities(conn, citizenlab: List[Dict]) -> None:
    q = "SELECT category_code, cc, domain, url, priority FROM url_priorities"
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        prio_rules = queryall(cur, q)

    assert citizenlab
    assert prio_rules
    match_attempt_cnt = 0
    match_cnt = 0
    for cz in citizenlab:
        cz["priority"] = 0
        for pr in prio_rules:
            match_attempt_cnt += 1
            if match_prio_rule(cz, pr):
                match_cnt += 1
                cz["priority"] += pr["priority"]

    perc = match_cnt / match_attempt_cnt * 100
    log.info(f"Prioritization rules match percentage {perc}")


# Priorities are computed only on citizenlab fetch from github
"""
def connect_db(c):
    return psycopg2.connect(
        dbname=c["dbname"], user=c["dbuser"], host=c["dbhost"], password=c["dbpassword"]
    )


def load_citizenlab(conn):
    q = "SELECT domain, url, cc, category_code, priority FROM citizenlab"
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        return queryall(cur, q)


# Manual run
def main():
    logging.basicConfig(level=logging.DEBUG)
    conn = connect_db(conf.active)
    citizenlab = load_citizenlab(conn)
    compute_url_priorities(conn, citizenlab)


if __name__ == "__main__":
    main()
"""
