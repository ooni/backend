"""
Fetch fingerprints from https://github.com/ooni/blocking-fingerprints
Populate 2 tables atomically using the citizenlab user.

Local test run:
    PYTHONPATH=analysis ./run_analysis --update-fingerprints --stdout
"""

from argparse import Namespace
from urllib.request import urlopen
import logging
import csv

from clickhouse_driver import Client as Clickhouse

from analysis.metrics import setup_metrics

BASE_URL = "https://raw.githubusercontent.com/"
HTTP_URL = f"{BASE_URL}/ooni/blocking-fingerprints/main/fingerprints_http.csv"
DNS_URL = f"{BASE_URL}/ooni/blocking-fingerprints/main/fingerprints_dns.csv"


log = logging.getLogger("analysis.fingerprints_updater")
metrics = setup_metrics(name="fingerprints_updater")
progress_cnt = 0


def progress(msg: str) -> None:
    global progress_cnt
    metrics.gauge("fingerprints_update_progress", progress_cnt)
    log.info(f"{progress_cnt} {msg}")
    progress_cnt += 1


@metrics.timer("fetch_csv")
def fetch_csv(url):
    resp = urlopen(url)
    if resp.status != 200:
        raise Exception(f"Failed to fetch {url}")
    lines = [x.decode("utf-8") for x in resp.readlines()]
    log.info(f"Fetched {len(lines)} lines")
    rows = csv.DictReader(lines)
    return [r for r in rows]


def update_fingerprints(conf: Namespace) -> None:
    progress("starting")
    assert not conf.dry_run, "Dry run mode not supported"
    click = Clickhouse.from_url(conf.db_uri)

    q = "DROP TABLE IF EXISTS fingerprints_dns_tmp"
    click.execute(q)

    q = """
    CREATE TABLE fingerprints_dns_tmp (
        name String,
        scope Enum('nat' = 1, 'isp' = 2, 'prod' = 3, 'inst' = 4, 'vbw' = 5, 'fp' = 6),
        other_names String,
        location_found String,
        pattern_type Enum('full' = 1, 'prefix' = 2, 'contains' = 3, 'regexp' = 4),
        pattern String,
        confidence_no_fp UInt8,
        expected_countries String,
        source String,
        exp_url String,
        notes String
    ) ENGINE = EmbeddedRocksDB PRIMARY KEY(name)
    """
    click.execute(q)
    progress("fingerprints_dns_tmp recreated")

    log.info(f"Ingesting {DNS_URL}")
    data = fetch_csv(DNS_URL)
    for row in data:
        row["confidence_no_fp"] = int(row["confidence_no_fp"])
    progress("CSV data fetched")

    q = """
    INSERT INTO fingerprints_dns_tmp
        (name, scope, other_names, location_found, pattern_type, pattern,
        confidence_no_fp, expected_countries, source, exp_url, notes)
    VALUES
    """
    click.execute(q, data)
    # click.execute(q, data, types_check=True)
    progress("fingerprints_dns_tmp filled")

    r = click.execute("SELECT count() FROM fingerprints_dns_tmp")
    row_cnt = r[0][0]
    metrics.gauge("fingerprints_dns_tmp_len", row_cnt)
    assert 100 < row_cnt < 50_000

    q = "DROP TABLE IF EXISTS fingerprints_http_tmp"
    click.execute(q)

    q = """
    CREATE TABLE fingerprints_http_tmp (
        name String,
        scope Enum('nat' = 1, 'isp' = 2, 'prod' = 3, 'inst' = 4, 'vbw' = 5, 'fp' = 6, 'injb' = 7, 'prov' = 8),
        other_names String,
        location_found String,
        pattern_type Enum('full' = 1, 'prefix' = 2, 'contains' = 3, 'regexp' = 4),
        pattern String,
        confidence_no_fp UInt8,
        expected_countries String,
        source String,
        exp_url String,
        notes String
    ) ENGINE = EmbeddedRocksDB PRIMARY KEY(name)
    """
    click.execute(q)
    progress("fingerprints_http_tmp recreated")

    log.info(f"Ingesting {HTTP_URL}")
    data = fetch_csv(HTTP_URL)
    for row in data:
        row["confidence_no_fp"] = int(row["confidence_no_fp"])
    progress("CSV data fetched")

    q = """
    INSERT INTO fingerprints_http_tmp
        (name, scope, other_names, location_found, pattern_type, pattern,
        confidence_no_fp, expected_countries, source, exp_url, notes)
    VALUES
    """
    click.execute(q, data)
    progress("fingerprints_http_tmp filled")

    r = click.execute("SELECT count() FROM fingerprints_dns_tmp")
    row_cnt = r[0][0]
    metrics.gauge("fingerprints_http_tmp_len", row_cnt)
    assert 100 < row_cnt < 50_000

    log.info("Swapping tables")
    q = "EXCHANGE TABLES fingerprints_dns_tmp AND fingerprints_dns"
    click.execute(q)
    progress("fingerprints_dns ready")

    log.info("Swapping tables")
    q = "EXCHANGE TABLES fingerprints_http_tmp AND fingerprints_http"
    click.execute(q)
    progress("fingerprints_http ready")
