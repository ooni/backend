#!/usr/bin/env python3
"""
Clickhouse feeder

Inputs:
    config file /etc/ooni/clickhouse_feeder.conf
    `fastpath` table from ams-pg.ooni.org
Outputs:
    `fastpath` table in clickhouse
    statsd metrics

Sync a chunk of rows from PG to CH, using a lockfile to avoid paraller runs
and a timestamp updated on success to ensure we copy everything even across
script restarts or errors.
fetchmany() and batched writes are used for performance. In case of crash
between writes we'll have duplicate writes in future runs but clickhouse will
deduplicate the rows.
Reconnect to DBs as needed.
"""

from datetime import datetime, timedelta
import logging
import time
from configparser import ConfigParser
from pathlib import Path

from filelock import FileLock  # debdeps: python3-filelock
import psycopg2  # debdeps: python3-psycopg2
import statsd

# debdeps: python3-clickhouse-driver
from clickhouse_driver import Client as Clickhouse
from systemd.journal import JournalHandler  # debdeps: python3-systemd

metrics = statsd.StatsClient("127.0.0.1", 8125, prefix="clickhouse_feeder")

log = logging.getLogger("analysis.clickhouse_feeder")


def setup_pg_connection(c):
    log.info("Connecting to PG")
    host = c["pg_dbhost"]
    if host == "localhost":
        conn = psycopg2.connect(dbname="metadb", user=c["pg_dbuser"])
    else:
        conn = psycopg2.connect(dbname="metadb", user=c["pg_dbuser"], host=c["pg_dbhost"])
    return conn


def setup_click_connection(c):
    log.info("Connecting to Clickhouse")
    return Clickhouse("localhost")


@metrics.timer("sync_clickhouse_fastpath")
def sync_clickhouse_fastpath(pg_conn, click_conn, old_tstamp, new_tstamp):
    sql_read = """SELECT
    measurement_uid,
    report_id,
    COALESCE(input, '') AS input,
    COALESCE(domain, '') AS domain,
    probe_cc,
    probe_asn,
    test_name,
    test_start_time,
    measurement_start_time,
    scores::text,
    platform,
    CASE WHEN anomaly THEN 't' ELSE 'f' END,
    CASE WHEN confirmed THEN 't' ELSE 'f' END,
    CASE WHEN msm_failure THEN 't' ELSE 'f' END,
    software_name,
    software_version

    FROM fastpath WHERE measurement_uid > %s and measurement_uid < %s
    """
    sql_write = """
    INSERT INTO fastpath (
    measurement_uid,
    report_id,
    input,
    domain,
    probe_cc,
    probe_asn,
    test_name,
    test_start_time,
    measurement_start_time,
    scores,
    platform,
    anomaly,
    confirmed,
    msm_failure,
    software_name,
    software_version
    ) VALUES
    """
    row_count = 0
    with pg_conn.cursor() as pg_cur:
        log.debug(f"Querying source PG {old_tstamp} {new_tstamp}")
        pg_cur.execute(sql_read, [old_tstamp, new_tstamp])
        while True:
            rows = pg_cur.fetchmany(10_000)
            row_count += len(rows)
            if not rows:
                metrics.gauge("sync_clickhouse_fastpath_cnt", row_count)
                return
            click_conn.execute(sql_write, rows)
            log.info(f"Inserted {len(rows)} rows into fastpath")


@metrics.timer("sync_clickhouse_jsonl")
def sync_clickhouse_jsonl(pg_conn, click_conn, old_tstamp, new_tstamp):
    read_pg = """SELECT
     report_id, input, s3path, linenum, COALESCE(measurement_uid, '')
    FROM jsonl
    WHERE measurement_uid > %s and measurement_uid < %s
    """
    write_click = """INSERT INTO jsonl (
        report_id, input, s3path, linenum, measurement_uid
    ) VALUES """

    row_count = 0
    with pg_conn.cursor() as pg_cur:
        log.debug(f"Querying PG jsonl {old_tstamp} {new_tstamp}")
        pg_cur.execute(read_pg, [old_tstamp, new_tstamp])
        while True:
            rows = pg_cur.fetchmany(10_000)
            row_count += len(rows)
            if not rows:
                metrics.gauge("sync_clickhouse_jsonl_cnt", row_count)
                return row_count > 0
            click_conn.execute(write_click, rows)
            log.info(f"Inserted {len(rows)} rows into jsonl")

    return row_count > 0


def main():
    delay = timedelta(seconds=10)
    log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="clickhouse_feeder"))
    log.setLevel(logging.DEBUG)
    cp = ConfigParser()
    with Path("/etc/ooni/clickhouse_feeder.conf").open() as f:
        cp.read_file(f)
    conf = dict(cp["DEFAULT"])
    log.info("Starting clickhouse_feeder")

    lockfile_f = Path("/var/lib/analysis/clickhouse_feeder.lock")
    tstamp_f = Path("/var/lib/analysis/clickhouse_feeder.tstamp")
    jsonl_tstamp_f = Path("/var/lib/analysis/clickhouse_feeder.jsonl.tstamp")
    pg_conn = setup_pg_connection(conf)
    click_conn = setup_click_connection(conf)
    while True:
        time.sleep(1)
        log.info("locking")
        with FileLock(lockfile_f):
            log.debug("lock acquired")
            try:
                old_tstamp = tstamp_f.read_text().strip()
                new_tstamp = datetime.utcnow() - delay
                new_tstamp = new_tstamp.strftime("%Y%m%d%H%M%S")
                if new_tstamp <= old_tstamp:
                    continue

                sync_clickhouse_fastpath(pg_conn, click_conn, old_tstamp, new_tstamp)
                # Update timestamp only on success
                tstamp_f.write_text(new_tstamp)

                # Update JSONL table
                old_tstamp = jsonl_tstamp_f.read_text().strip()
                new_tstamp = datetime.utcnow() - timedelta(minutes=80)
                new_tstamp = new_tstamp.strftime("%Y%m%d%H%M%S")
                if new_tstamp <= old_tstamp:
                    continue
                found = sync_clickhouse_jsonl(
                    pg_conn, click_conn, old_tstamp, new_tstamp
                )
                if found:  # Update timestamp only if data was found
                    jsonl_tstamp_f.write_text(new_tstamp)

            except psycopg2.OperationalError:
                log.warn("Reconnecting to PG")
                pg_conn = setup_pg_connection(conf)

            except Exception:
                log.error("Unhandled exception", exc_info=1)
                log.info("Reconnecting to PG")
                pg_conn = setup_pg_connection(conf)
                log.info("Reconnecting to Clickhouse")
                click_conn = setup_click_connection(conf)

            # except psycopg2.OperationalError:
            #    log.warn("Reconnecting to CH")
            #    click_conn =  setup_click_connection(conf)

            except ValueError as e:
                log.error(e)


if __name__ == "__main__":
    main()
