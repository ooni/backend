"""
Fetch test lists from https://github.com/citizenlab/test-lists

Populate citizenlab table from the tests lists and the input table

Populate the domain_input table

The tables are created in oometa/019-domain-and-citizenlab-table.install.sql

The tables have few constraints on the database side: most of the validation
is done here and it is meant to be strict.

On fastpath host, run: domain_input_updater -h

Local test run:
python3 fastpath/domain_input.py --db-uri 'host=localhost user=shovel dbname=metadb' --dry-run
"""

from argparse import ArgumentParser
from os import unlink
from pathlib import Path
from subprocess import check_call
from tempfile import TemporaryDirectory, mkstemp
from typing import List, Set, Dict, Tuple, Optional
import csv
import logging
import re
import sys

from psycopg2.extras import execute_values

import fastpath.db as db
from fastpath.metrics import setup_metrics


HTTPS_GIT_URL = "https://github.com/citizenlab/test-lists.git"

log = logging.getLogger("fastpath.domain_input")
metrics = setup_metrics(name="fastpath.domain_input")


VALID_URL = re.compile(
    r"(^(?:http)s?://)?"  # http:// or https://
    r"((?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}))"  # ...or ipaddr
    r"(?::\d+)?"  # optional port
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)

URL_BAD_CHARS = {"\r", "\n", "\t", "\\"}


def _extract_domain(url: str) -> Optional[str]:
    if any(c in URL_BAD_CHARS for c in url):
        return None

    m = VALID_URL.match(url)
    if m:
        return m.group(2)


@metrics.timer("fetch_citizen_lab_lists")
def fetch_citizen_lab_lists():
    """Clone repository in a temporary directory and extract files
    """
    out = []  # (cc or "ZZ", domain, url, category_code)
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
                    out.append((cc, domain, url, item["category_code"]))

    return out


@metrics.timer("rebuild_citizenlab_table_from_citizen_lab_lists")
def rebuild_citizenlab_table_from_citizen_lab_lists(conf):
    """Fetch lists from GitHub repository
    """
    ev = "INSERT INTO citizenlab (cc, domain, url, category_code) VALUES %s"

    test_items = fetch_citizen_lab_lists()

    with db.conn.cursor() as cur:
        log.info("Truncating citizenlab table")
        cur.execute("TRUNCATE citizenlab")
        log.info("Inserting %d citizenlab table entries", len(test_items))
        execute_values(cur, ev, test_items)

    if conf.dry_run:
        db.conn.rollback()
    else:
        db.conn.commit()
    log.info("citizenlab_table is ready")


@metrics.timer("rebuild_domain_input_table")
def rebuild_domain_input_table(conf):
    """Load data from input table in large batches
    Validate input and write domain, input, input_no into domain_input
    """
    _, csv_fname = mkstemp()

    with db.conn.cursor() as cur:
        log.info("Truncating domain_input")
        cur.execute("TRUNCATE domain_input")

        log.info("Fetching from input table")
        cur.execute("SELECT input, input_no FROM input")
        with open(csv_fname, "w", newline="") as csv_f:
            csv_writer = csv.writer(csv_f, delimiter="\t")
            valid_cnt = 0
            invalid_cnt = 0
            while True:
                # Iterate across chunks of rows
                rows = cur.fetchmany(10000)
                if not rows:
                    break

                log.debug("Fetched %d rows", len(rows))
                for input_, input_no in rows:
                    domain = _extract_domain(input_)
                    if domain:
                        csv_writer.writerow([domain, input_, input_no])
                        valid_cnt += 1
                    else:
                        log.debug("Ignoring input %r", input_)
                        invalid_cnt += 1

            log.info("Filling domain_input with %d bytes", csv_f.tell())
            log.info(
                "Valid inputs: %d invalid: %d invalid percentage: %f",
                valid_cnt,
                invalid_cnt,
                invalid_cnt * 100.0 / (valid_cnt + invalid_cnt),
            )

        with open(csv_fname, newline="") as f:
            cur.copy_from(f, "domain_input", columns=("domain", "input", "input_no"))

        if conf.dry_run:
            log.info("Leaving %s on disk", csv_fname)
        else:
            unlink(csv_fname)

    if conf.dry_run:
        db.conn.rollback()
    else:
        db.conn.commit()
    log.info("domain_input is ready")


def run(conf) -> None:
    db.setup(conf)
    rebuild_citizenlab_table_from_citizen_lab_lists(conf)
    rebuild_domain_input_table(conf)


def main():
    logf = "%(relativeCreated)d %(process)d %(levelname)s %(name)s %(message)s"
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=logf)

    ap = ArgumentParser(__doc__)
    ap.add_argument("--db-uri", help="Database DSN or URI. The string is logged!")
    ap.add_argument(
        "--dry-run", action="store_true", help="Rollback instead of committing"
    )
    conf = ap.parse_args()
    run(conf)


if __name__ == "__main__":
    main()
