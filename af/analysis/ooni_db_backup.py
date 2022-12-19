#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OONI DB backup tool
Configured with /etc/ooni/db-backup.conf - Runs as a system daemon
Inputs: Clickhouse database tables

Backup database schema and tables to S3 without using temporary files.
Compress data.
Chunk tables as needed and add sleeps to prevent query backlog.

Monitor with:  sudo journalctl -f --identifier ooni-db-backup

Metrix prefix: db-backup
"""

# Compatible with Python3.9 - linted with Black

import json
import logging
import sys

from time import perf_counter, sleep

try:
    from systemd.journal import JournalHandler  # debdeps: python3-systemd

    has_systemd = True
except ImportError:
    has_systemd = False  # macOS

from analysis.metrics import setup_metrics  # debdeps: python3-statsd
from clickhouse_driver import Client as Clickhouse

metrics = setup_metrics(name="db-backup")
log = logging.getLogger("ooni-db-backup")

# TODO backup schema

# backup implemented in release 22.10, 2022-10-25
sql_base = """
    BACKUP TABLE %(tblname)s TO
    S3(%(s3path_base)s, %(aws_id)s, %(aws_secret)s)
    SETTINGS compression_method='lzma', compression_level=3
"""
sql_incremental = """
    BACKUP TABLE %(tblname)s TO
    S3(%(s3path_incremental)s, %(aws_id)s, %(aws_secret)s)
    SETTINGS
    base_backup = S3(%(s3path_base)s, %(aws_id)s, %(aws_secret)s)
    compression_method='lzma', compression_level=3
"""


@metrics.timer("run_backup")
def run_backup(conf) -> None:
    aws_id = conf["public_aws_access_key_id"]
    aws_secret = conf["public_aws_secret_access_key"]
    bucket_name = conf["public_bucket_name"]
    baseurl = f"https://{bucket_name}.s3.amazonaws.com/clickhouse_backup/"
    click = Clickhouse.from_url(conf["clickhouse_url"])

    for tblname, tbl_setting in conf["tables"].items():
        if tbl_setting == "ignore":
            log.info(f"Skipping {tblname}")
            continue
        elif tbl_setting == "full":
            sql = sql_base
        elif tbl_setting == "incremental":
            sql = sql_incremental
        else:
            log.error(f"Skipping {tblname} unknown value {tbl_setting}")
            continue

        log.info(f"backing up {tblname}")
        t0 = perf_counter()

        s3path_base = f"{baseurl}/{tblname}__base.bkp"
        s3path_incremental = f"{baseurl}/{tblname}__incremental.bkp"

        kw = dict(
            aws_id=aws_id,
            aws_secret=aws_secret,
            s3path_base=s3path_base,
            s3path_incremental=s3path_incremental,
            tblname=tblname,
        )
        click.execute(sql, kw)

        delta_ms = int((perf_counter() - t0) * 1000)
        metrics.timing(f"table_{tblname}", delta_ms)
        log.info("table backup completed")


def describe_table(click, tblname):
    assert " " not in tblname
    assert "'" not in tblname
    colnames = []
    blob = []
    for row in click.execute(f"DESCRIBE TABLE {tblname}"):
        colname, coltype = row[:2]
        colnames.append(colname)
        blob.append(f"{colname} {coltype}")

    assert colnames
    s_blob = ", ".join(blob)  # "measurement_uid String report_id String, ... "
    s_colnames = ", ".join(colnames)  # "measurement_uid, report_id, ... "
    return s_colnames, s_blob


def export_fastpath(click, aws_id: str, aws_secret: str, baseurl: str) -> None:
    tblname = "fastpath"
    s_colnames, s_blob = describe_table(click, tblname)
    assert s_blob.startswith("measurement_uid String, ")
    # s_colnames is a string to be placed into ##colnames## without quotes
    basesql = """
    INSERT INTO FUNCTION s3(%(s3path)s, %(aws_id)s, %(aws_secret)s,
        'CSVWithNames',
        %(s_blob)s
    )
    SELECT ##colnames##
    FROM fastpath
    WHERE toYYYYMM(measurement_start_time) = %(yyyymm)s
    SETTINGS s3_max_connections=4, max_insert_threads=4,
    s3_min_upload_part_size=50100100;
    """
    delta_ms = 0
    for year in range(2012, 2024):
        for month in range(1, 13):
            yyyymm = f"{year}{month:02}"
            s3path = f"{baseurl}/csv/{tblname}_{yyyymm}.csv.zstd"
            kw = dict(
                aws_id=aws_id,
                aws_secret=aws_secret,
                s3path=s3path,
                yyyymm=yyyymm,
                s_blob=s_blob,
            )
            sql = basesql.replace("##colnames##", s_colnames)
            log.info(f"exporting {tblname} {yyyymm}")
            t0 = perf_counter()
            log.info(sql)
            click.execute(sql, kw)
            delta_ms += int((perf_counter() - t0) * 1000)
            metrics.gauge(f"table_{tblname}_backup_time_ms", delta_ms)
            sleep(10)

    log.info("table backup completed")


def export_jsonl(click, aws_id: str, aws_secret: str, baseurl: str) -> None:
    tblname = "jsonl"
    s_colnames, s_blob = describe_table(click, tblname)
    assert s_blob.startswith("report_id String, ")
    # s_colnames is a string to be placed into ##colnames## without quotes.
    # jsonl is indexed by report_id: chuck using LIMIT / OFFSET instead
    basesql = """
    INSERT INTO FUNCTION s3(%(s3path)s, %(aws_id)s, %(aws_secret)s,
        'CSVWithNames',
        %(s_blob)s
    )
    SELECT ##colnames##
    FROM jsonl
    SETTINGS s3_max_connections=4, max_insert_threads=4,
    s3_min_upload_part_size=50100100;
    """
    delta_ms = 0
    chunk_size = 100_000_000
    chunk_num = 0
    while True:
        s3path = f"{baseurl}/csv/{tblname}_{chunk_num:05}.csv.zstd"
        kw = dict(
            aws_id=aws_id,
            aws_secret=aws_secret,
            s3path=s3path,
            limit=chunk_size,
            offset=chunk_num * chunk_size,
            s_blob=s_blob,
        )
        sql = "SELECT count() FROM jsonl LIMIT %(limit)s OFFSET %(offset)s"
        r = click.execute(sql, kw)
        if not r or not r[0][0]:
            break

        sql = basesql.replace("##colnames##", s_colnames)
        log.info(f"exporting {tblname} chunk {chunk_num}")
        t0 = perf_counter()
        log.info(sql)
        r = click.execute(sql, kw)
        delta_ms += int((perf_counter() - t0) * 1000)
        metrics.gauge(f"table_{tblname}_backup_time_ms", delta_ms)
        chunk_num += 1
        sleep(10)

    log.info("table backup completed")


def export_table(
    click, aws_id: str, aws_secret: str, baseurl: str, tblname: str
) -> None:
    """Export small table as CSV.zstd without chunking"""
    s_colnames, s_blob = describe_table(click, tblname)
    # s_colnames is a string to be placed into ##colnames## without quotes.
    basesql = """
    INSERT INTO FUNCTION s3(%(s3path)s, %(aws_id)s, %(aws_secret)s,
        'CSVWithNames',
        %(s_blob)s
    )
    SELECT ##colnames##
    FROM ##tblname##
    SETTINGS s3_max_connections=4, max_insert_threads=4,
    s3_min_upload_part_size=50100100;
    """
    s3path = f"{baseurl}/csv/{tblname}.csv.zstd"
    kw = dict(
        aws_id=aws_id,
        aws_secret=aws_secret,
        s3path=s3path,
        s_blob=s_blob,
    )
    sql = basesql.replace("##colnames##", s_colnames)
    sql = sql.replace("##tblname##", tblname)
    log.info(f"exporting {tblname} as {s3path}")
    log.info(sql)
    t0 = perf_counter()
    r = click.execute(sql, kw)
    delta_ms = int((perf_counter() - t0) * 1000)
    metrics.gauge(f"table_{tblname}_backup_time_ms", delta_ms)
    log.info("table backup completed")


@metrics.timer("run_export")
def run_export(conf) -> None:
    """Export tables to S3 as zstd compressed CSV with colum names
    """
    aws_id = conf["public_aws_access_key_id"]
    aws_secret = conf["public_aws_secret_access_key"]
    bucket_name = conf["public_bucket_name"]
    baseurl = f"https://{bucket_name}.s3.amazonaws.com/clickhouse_export/"
    click = Clickhouse.from_url(conf["clickhouse_url"])

    export_fastpath(click, aws_id, aws_secret, baseurl)
    export_jsonl(click, aws_id, aws_secret, baseurl)

    tblnames = ("citizenlab", "msmt_feedback")
    for tblname in tblnames:
        export_table(click, aws_id, aws_secret, baseurl, tblname)
        sleep(5)

    return #FIXME
    aws_id = conf["private_aws_access_key_id"]
    aws_secret = conf["private_aws_secret_access_key"]
    bucket_name = conf["private_bucket_name"]
    tblnames = ("test_helper_instances" "url_priorities")
    for tblname in tblnames:
        export_table(click, aws_id, aws_secret, baseurl, tblname)
        sleep(5)


def main() -> None:
    if has_systemd:
        log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="ooni-db-backup"))
        log.setLevel(logging.DEBUG)
    else:
        format = "%(relativeCreated)d %(process)d %(levelname)s %(name)s %(message)s"
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=format)
    log.info("Backup tool starting")
    metrics.gauge("status", 1)
    try:
        with open("/etc/ooni/db-backup.conf") as f:
            conf = json.load(f)

        if conf["action"] == "export":
            run_export(conf)
        else:
            run_backup(conf)
    except Exception as e:
        metrics.gauge("status", 2)
        log.error(e, exc_info=True)
        return

    metrics.gauge("status", 0)
    log.info("done")


if __name__ == "__main__":
    main()
