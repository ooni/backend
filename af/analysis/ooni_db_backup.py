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
import os
import os.path
import subprocess
import sys

from time import perf_counter, sleep

import boto3  # debdeps: python3-boto3

try:
    from systemd.journal import JournalHandler  # debdeps: python3-systemd

    has_systemd = True
except ImportError:
    has_systemd = False  # macOS

from analysis.metrics import setup_metrics  # debdeps: python3-statsd
from clickhouse_driver import Client as Clickhouse

for x in ("urllib3", "botocore", "s3transfer"):
    logging.getLogger(x).setLevel(logging.INFO)


metrics = setup_metrics(name="db-backup")
log = logging.getLogger("ooni-db-backup")

# TODO: backup schema

# TODO: move to the native BACKUP syntax
# implemented in release 22.10, 2022-10-25
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


# #  currently unused # #
@metrics.timer("run_backup")
def run_backup(conf) -> None:
    aws_id = conf["public_aws_access_key_id"]
    aws_secret = conf["public_aws_secret_access_key"]
    bucket_name = conf["public_bucket_name"]
    baseurl = f"https://{bucket_name}.s3.amazonaws.com/clickhouse_backup/"
    click = Clickhouse.from_url(conf["clickhouse_url"])

    for tblname, tbl_setting in conf["backup_tables"].items():
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


def fastpath_has_rows(click, yyyymm) -> bool:
    sql = """SELECT count() FROM fastpath
    WHERE toYYYYMM(measurement_start_time) = %(yyyymm)s"""
    s = click.execute(sql, dict(yyyymm=yyyymm))
    if not s:
        return False
    return s[0][0] > 0


def query_with_retries(click, sql: str, kw: dict, pause_s=5, tries=100) -> float:
    """Try query `tries` times. Return query duration"""
    for try_n in range(tries):
        try:
            t0 = perf_counter()
            click.execute(sql, kw)
            return perf_counter() - t0
        except Exception as e:
            log.error(e)
            if try_n == (tries - 1):
                raise e
            log.info("retrying")
            sleep(pause_s)


def export_fastpath(click, s3_client, bucket_name: str, data_cnt: int) -> int:
    """Exports fastpath to a set of CSV.zstd files on S3.
    Chunk table across the primary index to prevent heavy queries.
    """
    tblname = "fastpath"
    # TODO use dedicated directory
    t0 = perf_counter()
    for year in range(2012, 2030):
        for month in range(1, 13):
            yyyymm = f"{year}{month:02}"
            if not fastpath_has_rows(click, yyyymm):
                log.info(f"Skipping {yyyymm}: no rows")
                continue

            tmpfn = f"/tmp/clickhouse_{tblname}_{yyyymm}.csv.zstd"
            try:
                os.remove(tmpfn)
                log.info(f"Leftover {tmpfn} removed")
            except FileNotFoundError:
                pass
            cmd = f"""clickhouse-client -q "SELECT * FROM fastpath WHERE toYYYYMM(measurement_start_time) = '{yyyymm}' FORMAT CSVWithNames" | zstd > {tmpfn}"""
            log.info(f"exporting {tblname} {yyyymm}")
            log.info(cmd)
            subprocess.check_output(cmd, shell=True)
            s3path = f"clickhouse_export/csv/{tblname}_{yyyymm}.csv.zstd"
            size = upload_to_s3(s3_client, bucket_name, tmpfn, s3path)
            os.remove(tmpfn)

            data_cnt += size
            metrics.gauge("uploaded_bytes_tot", data_cnt)
            delta_ms = int((perf_counter() - t0) * 1000)
            metrics.gauge(f"table_{tblname}_backup_time_ms", delta_ms)
            sleep(5)

    log.info(f"{tblname} table backup completed")
    return data_cnt


def export_jsonl(click, s3_client, bucket_name: str, data_cnt: int) -> int:
    """Exports jsonl to a set of CSV.zstd files on S3.
    Chunk table to prevent heavy queries and large files.
    """
    tblname = "jsonl"
    chunk_size = 100_000_000
    chunk_num = 0
    done = False
    # TODO use dedicated directory
    t0 = perf_counter()
    while True:
        tmpfn = f"/tmp/clickhouse_{tblname}_{chunk_num}.csv.zstd"
        try:
            os.remove(tmpfn)
            log.info(f"Leftover {tmpfn} removed")
        except FileNotFoundError:
            pass
        off = chunk_num * chunk_size
        cmd = f"""clickhouse-client -q "SELECT * FROM jsonl LIMIT {chunk_size} OFFSET {off} FORMAT CSVWithNames" | zstd > {tmpfn}"""
        log.info(f"exporting {tblname} {chunk_size}")
        log.info(cmd)
        subprocess.check_output(cmd, shell=True)
        size = os.path.getsize(tmpfn)
        if size > 120:
            # hacky threshold that should work reliably unless we add many
            # more columns to the table
            s3path = f"clickhouse_export/csv/{tblname}_{chunk_num}.csv.zstd"
            size = upload_to_s3(s3_client, bucket_name, tmpfn, s3path)
        else:
            done = True

        os.remove(tmpfn)

        data_cnt += size
        metrics.gauge("uploaded_bytes_tot", data_cnt)
        delta_ms = int((perf_counter() - t0) * 1000)
        metrics.gauge(f"table_{tblname}_backup_time_ms", delta_ms)
        if done:
            break
        sleep(5)
        chunk_num += 1

    log.info(f"{tblname} table backup completed")
    return data_cnt


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
    click.execute(sql, kw)
    delta_ms = int((perf_counter() - t0) * 1000)
    metrics.gauge(f"table_{tblname}_backup_time_ms", delta_ms)
    log.info(f"{tblname} table backup completed")


def create_s3_client(aws_id: str, aws_secret: str):
    return boto3.client(
        "s3",
        aws_access_key_id=aws_id,
        aws_secret_access_key=aws_secret,
    )


@metrics.timer("upload_to_s3")
def upload_to_s3(s3_client, bucket_name: str, fn: str, s3path: str) -> int:
    size = os.path.getsize(fn)
    log.info(f"Uploading {s3path} to S3. Size: {size / 2**20} MB")
    s3_client.upload_file(fn, bucket_name, s3path)
    log.info("Upload completed")
    return size


@metrics.timer("run_export")
def run_export(conf) -> None:
    """Export tables to S3 as zstd compressed CSV with colum names"""
    aws_id = conf["public_aws_access_key_id"]
    aws_secret = conf["public_aws_secret_access_key"]
    bucket_name = conf["public_bucket_name"]
    click = Clickhouse.from_url(conf["clickhouse_url"])
    s3_client = create_s3_client(aws_id, aws_secret)

    # "INSERT INTO FUNCTION s3(...)" fails on large tables so we use a
    # temporary file instead.
    data_cnt = 0
    data_cnt = export_fastpath(click, s3_client, bucket_name, data_cnt)
    data_cnt = export_jsonl(click, s3_client, bucket_name, data_cnt)

    # Export small tables
    # baseurl = f"https://{bucket_name}.s3.amazonaws.com/clickhouse_export/"
    # tblnames = ("citizenlab",)
    # for tblname in tblnames:
    #     export_table(click, aws_id, aws_secret, baseurl, tblname)
    #     sleep(5)


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
