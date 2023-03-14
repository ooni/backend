"""
Fetch asn metadata from https://archive.org/download/ip2country-as (generated via: https://github.com/ooni/historical-geoip)

Local test run:
    PYTHONPATH=analysis ./run_analysis --update-asnmeta --stdout
"""

from argparse import Namespace
from datetime import datetime
from urllib.request import urlopen
import logging
import json

from clickhouse_driver import Client as Clickhouse

from analysis.metrics import setup_metrics

AS_ORG_MAP_URL = "https://archive.org/download/ip2country-as/all_as_org_map.json"

log = logging.getLogger("analysis.asnmeta_updater")
metrics = setup_metrics(name="asnmeta_updater")
progress_cnt = 0


def progress(msg: str) -> None:
    global progress_cnt
    metrics.gauge("asnmeta_update_progress", progress_cnt)
    log.info(f"{progress_cnt} {msg}")
    progress_cnt += 1


@metrics.timer("fetch_data")
def fetch_data():
    resp = urlopen(AS_ORG_MAP_URL)
    if resp.status != 200:
        raise Exception(f"Failed to fetch {url}")
    j = json.load(resp)
    rows = []
    for asn, history in j.items():
        asn = int(asn)
        for v in history:
            rows.append(
                {
                    "asn": asn,
                    "org_name": v[0],
                    "cc": v[1],
                    "changed": datetime.strptime(v[2], "%Y%m%d").date(),
                    "aut_name": v[3],
                    "source": v[4],
                }
            )
    del j
    return rows


def update_asnmeta(conf: Namespace) -> None:
    progress("starting")
    assert not conf.dry_run, "Dry run mode not supported"
    click = Clickhouse.from_url(conf.db_uri)

    q = "DROP TABLE IF EXISTS asnmeta_tmp"
    click.execute(q)

    q = """
    CREATE TABLE asnmeta_tmp (
        asn UInt32,
        org_name String,
        cc String,
        changed Date,
        aut_name String,
        source String
    ) ENGINE = MergeTree()
    ORDER BY (asn, changed)
    """
    click.execute(q)
    progress("asnmeta_tmp recreated")

    log.info(f"Ingesting {AS_ORG_MAP_URL}")
    data = fetch_data()
    progress("JSON data fetched")

    q = """
    INSERT INTO asnmeta_tmp
        (asn, org_name, cc, changed, aut_name, source)
    VALUES
    """
    click.execute(q, data)
    progress("asnmeta_tmp filled")

    r = click.execute("SELECT count() FROM asnmeta_tmp")
    row_cnt = r[0][0]
    metrics.gauge("asnmeta_tmp_len", row_cnt)
    assert 100_000 < row_cnt < 1_000_000

    log.info("Swapping tables")
    q = "EXCHANGE TABLES asnmeta_tmp AND asnmeta"
    click.execute(q)
    progress("asnmeta ready")
