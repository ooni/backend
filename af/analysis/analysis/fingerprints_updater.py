"""
Fetch fingerprints from https://github.com/ooni/blocking-fingerprints
Populate 2 tables atomically using the citizenlab user.

Local test run:
    PYTHONPATH=analysis ./run_analysis --update-fingerprints --stdout
"""

from argparse import Namespace
import logging

from clickhouse_driver import Client as Clickhouse

from analysis.metrics import setup_metrics

BASE_URL = "https://raw.githubusercontent.com/"
HTTP_URL = f"{BASE_URL}/ooni/blocking-fingerprints/main/fingerprints_http.csv"
DNS_URL = f"{BASE_URL}/ooni/blocking-fingerprints/main/fingerprints_dns.csv"


log = logging.getLogger("analysis.fingerprints_updater")
metrics = setup_metrics(name="fingerprints_updater")


def progress(n: int, msg: str) -> None:
    metrics.gauge("fingerprints_update_progress", n)
    log.info(msg)


def update_fingerprints(conf: Namespace) -> None:
    progress(0, "starting")
    assert not conf.dry_run, "Dry run mode not supported"
    click = Clickhouse("localhost", user="citizenlab")

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

    log.info(f"Ingesting {DNS_URL}")
    q = """
    INSERT INTO fingerprints_dns_tmp
    SELECT * FROM url(%(url)s, 'CSVWithNames',
    'name String,
    scope String,
    other_names String,
    location_found String,
    pattern_type String,
    pattern String,
    confidence_no_fp UInt8,
    expected_countries String,
    source String,
    exp_url String,
    notes String'
    )
    """
    click.execute(q, dict(url=DNS_URL))
    progress(1, "fingerprints_dns_tmp filled")

    r = click.execute("SELECT count() FROM fingerprints_dns_tmp")
    row_cnt = r[0][0]
    metrics.gauge("fingerprints_dns_tmp_len", row_cnt)
    assert 100 < row_cnt < 50_000

    q = "DROP TABLE IF EXISTS fingerprints_http_tmp"
    click.execute(q)

    # FIXME remove injb and prov
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

    log.info(f"Ingesting {HTTP_URL}")
    q = """
    INSERT INTO fingerprints_http_tmp
    SELECT * FROM url(%(url)s, 'CSVWithNames',
    'name String,
    scope String,
    other_names String,
    location_found String,
    pattern_type String,
    pattern String,
    confidence_no_fp UInt8,
    expected_countries String,
    source String,
    exp_url String,
    notes String'
    )
    """
    click.execute(q, dict(url=HTTP_URL))
    progress(2, "fingerprints_http_tmp filled")

    r = click.execute("SELECT count() FROM fingerprints_dns_tmp")
    row_cnt = r[0][0]
    metrics.gauge("fingerprints_http_tmp_len", row_cnt)
    assert 100 < row_cnt < 50_000

    log.info("Swapping tables")
    q = "EXCHANGE TABLES fingerprints_dns_tmp AND fingerprints_dns"
    click.execute(q)
    progress(3, "fingerprints_dns ready")

    log.info("Swapping tables")
    q = "EXCHANGE TABLES fingerprints_http_tmp AND fingerprints_http"
    click.execute(q)
    progress(4, "fingerprints_http ready")
