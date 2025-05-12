#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""ooni-pipeline: * -> Analysis

Configured with /etc/analysis.conf

Runs as a system daemon but can also be used from command line in devel mode

Creates and updates unlogged tables.
Shows confirmed correlated by country, ASN, input URL over time.

Inputs: Database tables:
    countries

Outputs:
    Files in /var/lib/analysis
    Dedicated unlogged database tables and charts
        tables:


"""

# Compatible with Python3.9 - linted with Black

# TODO:
# Enable unused code
# Switch print() to logging
# Overall datapoints count per country per day
# Add ASN to confirmed_stats and use one table only if performance is
# acceptable.
# Move slicing and manipulation entirely in Pandas and drop complex SQL queries
# Support feeder.py for continuous ingestion
# Implement a crude precision metric based on msm_count and time window

from argparse import ArgumentParser, Namespace
from configparser import ConfigParser
from pathlib import Path
import os
import logging
import sys


try:
    from systemd.journal import JournalHandler  # debdeps: python3-systemd

    has_systemd = True
except ImportError:
    # this will be the case on macOS for example
    has_systemd = False

from analysis.metrics import setup_metrics  # debdeps: python3-statsd

from analysis.citizenlab_test_lists_updater import update_citizenlab_test_lists
from analysis.fingerprints_updater import update_fingerprints
from analysis.asnmeta_updater import update_asnmeta


# Global conf
conf = Namespace()

log = logging.getLogger("analysis")
metrics = setup_metrics(name="analysis")
DEFAULT_DB_URI = "clickhouse://api:api@localhost/default"
CONF_FILE = Path("/etc/ooni/analysis.conf")
DEV_CONF_FILE = Path(os.getcwd()) / "analysis.conf"


def parse_args() -> Namespace:
    ap = ArgumentParser("Analysis script " + __doc__)
    ap.add_argument(
        "--update-citizenlab", action="store_true", help="Update citizenlab test lists"
    )
    ap.add_argument(
        "--update-fingerprints", action="store_true", help="Update fingerprints"
    )
    ap.add_argument("--update-asnmeta", action="store_true", help="Update asn metadata")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run, supported only by some commands",
    )
    # ap.add_argument("--", action="store_true", help="")
    ap.add_argument("--devel", action="store_true", help="Devel mode")
    ap.add_argument("--stdout", action="store_true", help="Log to stdout")
    ap.add_argument("--db-uri", help="Override DB URI")
    
    return ap.parse_args()


def setup():
    global conf

    conf = parse_args()

    # Set up logs
    if conf.devel or conf.stdout or not has_systemd:
        format = "%(relativeCreated)d %(process)d %(levelname)s %(name)s %(message)s"
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=format)
    else:
        log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="analysis"))
        log.setLevel(logging.DEBUG)

    log.info("Logging started")

    conf.output_directory = (
        Path("./var/lib/analysis") if conf.devel else Path("/var/lib/analysis")
    )
    os.makedirs(conf.output_directory, exist_ok=True)

    # Parse configs
    conf_file = DEV_CONF_FILE if conf.devel else CONF_FILE

    # nothing else to do if there's no config to parse
    if not conf_file.exists():
        conf.db_uri = DEFAULT_DB_URI
        return     

    cp = ConfigParser()
    with conf_file.open("r") as f:
        cp.read_file(f)
        # Priorities: 
        # 1. CLI argument (override)
        # 2. Config 
        # 3. Default DB URI
        if "DB" not in cp: 
            conf.db_uri = conf.db_uri or DEFAULT_DB_URI
        else:
            conf.db_uri = conf.db_uri or cp['DB'].get("uri") or DEFAULT_DB_URI

        conf.table_names = cp['backup'].get("table_names", "").split()

def main() -> None:
    global conf
    log.info("Analysis starting")
    setup()

    try:
        if conf.update_citizenlab:
            update_citizenlab_test_lists(conf)
        elif conf.update_fingerprints:
            update_fingerprints(conf)
        elif conf.update_asnmeta:
            update_asnmeta(conf)

    except Exception as e:
        log.error(str(e), exc_info=e)

    log.info("done")


if __name__ == "__main__":
    main()
