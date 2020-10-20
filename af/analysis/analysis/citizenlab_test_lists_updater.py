"""
Fetch test lists from https://github.com/citizenlab/test-lists

Populate citizenlab table from the tests lists and the input table

Populate the domain_input table

The tables are created in oometa/019-domain-and-citizenlab-table.install.sql

The tables have few constraints on the database side: most of the validation
is done here and it is meant to be strict.

Local test run:
    PYTHONPATH=analysis ./run_analysis --update-citizenlab --dry-run --stdout

"""

from pathlib import Path
from subprocess import check_call
from tempfile import TemporaryDirectory
from typing import List, Tuple, Optional
import csv
import logging
import re

import psycopg2
from psycopg2.extras import execute_values

from analysis.metrics import setup_metrics


HTTPS_GIT_URL = "https://github.com/citizenlab/test-lists.git"

log = logging.getLogger("citizenlab_test_lists_updater")
metrics = setup_metrics(name="citizenlab_test_lists_updater")


VALID_URL = re.compile(
    r"(^(?:http)s?://)?"  # http:// or https://
    r"((?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}))"  # ...or ipaddr
    r"(?::\d+)?"  # optional port
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)

URL_BAD_CHARS = {"\r", "\n", "\t", "\\"}

# FIXME: temporarily hardcoded here for backend#361
PRIORITIES = {
    "NEWS": 100,
    "POLR": 100,
    "HUMR": 100,
    "LGBT": 100,
    "ANON": 100,
    "GRP": 80,
    "COMT": 80,
    "MMED": 80,
    "SRCH": 80,
    "PUBH": 80,
    "REL": 60,
    "XED": 60,
    "HOST": 60,
    "ENV": 60,
    "FILE": 40,
    "CULTR": 40,
    "IGO": 40,
    "GOVT": 40,
    "DATE": 30,
    "HATE": 30,
    "MILX": 30,
    "PROV": 30,
    "PORN": 30,
    "GMB": 30,
    "ALDR": 30,
    "GAME": 20,
    "MISC": 20,
    "HACK": 20,
    "ECON": 20,
    "COMM": 20,
    "CTRL": 20,
}


def _extract_domain(url: str) -> Optional[str]:
    if any(c in URL_BAD_CHARS for c in url):
        return None

    m = VALID_URL.match(url)
    if m:
        return m.group(2)

    return None


def connect_db(c):
    return psycopg2.connect(
        dbname=c["dbname"], user=c["dbuser"], host=c["dbhost"], password=c["dbpassword"]
    )


@metrics.timer("fetch_citizen_lab_lists")
def fetch_citizen_lab_lists() -> List[Tuple[str, str, str, str, int]]:
    """Clone repository in a temporary directory and extract files"""
    out = []  # (cc or "ZZ", domain, url, category_code, priority)
    with TemporaryDirectory() as tmpdir:
        cmd = ("git", "clone", "--depth", "1", HTTPS_GIT_URL, tmpdir)
        check_call(cmd, timeout=120)
        p = Path(tmpdir) / "lists"
        for i in sorted(p.glob("*.csv")):
            cc = i.stem
            if cc == "global":
                cc = "ZZ"
            if len(cc) != 2:
                continue
            log.info("Processing %s", i.name)
            with i.open() as f:
                for item in csv.DictReader(f):
                    url = item["url"]
                    domain = _extract_domain(url)
                    if not domain:
                        log.debug("Ignoring", url)
                        continue
                    category_code = item["category_code"]
                    priority = PRIORITIES.get(category_code, 100)
                    out.append((cc, domain, url, category_code, priority))

    return out


@metrics.timer("rebuild_citizenlab_table_from_citizen_lab_lists")
def rebuild_citizenlab_table_from_citizen_lab_lists(conf, conn):
    """Fetch lists from GitHub repository"""
    ev = "INSERT INTO citizenlab (cc, domain, url, category_code, priority) VALUES %s"

    test_items = fetch_citizen_lab_lists()

    with conn.cursor() as cur:
        log.info("Truncating citizenlab table")
        cur.execute("TRUNCATE citizenlab")
        log.info("Inserting %d citizenlab table entries", len(test_items))
        metrics.gauge("rowcount", len(test_items))
        execute_values(cur, ev, test_items)

    if conf.dry_run:
        log.info("rollback")
        conn.rollback()
    else:
        log.info("commit")
        conn.commit()
        log.info("citizenlab_table is ready")


def update_citizenlab_test_lists(conf) -> None:
    log.info("update_citizenlab_test_lists")
    conn = connect_db(conf.active)
    rebuild_citizenlab_table_from_citizen_lab_lists(conf, conn)
