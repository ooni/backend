#!/usr/bin/env python3
"""
Uploads OONI API measurements to S3
Reads /etc/ooni/api.conf
"""

from configparser import ConfigParser
from pathlib import Path
from datetime import datetime, timedelta
import gzip
import logging
import tarfile
import yaml

import ujson
import boto3
import psycopg2  # debdeps: python3-psycopg2
from psycopg2.extras import execute_values
import statsd  # debdeps: python3-statsd

metrics = statsd.StatsClient("127.0.0.1", 8125, prefix="ooni_api_uploader")
log = logging.getLogger("ooni_api_uploader")

try:
    from systemd.journal import JournalHandler  # debdeps: python3-systemd

    log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="ooni_api_uploader"))
except ImportError:
    pass

log.setLevel(logging.DEBUG)


def create_s3_client(conf):
    session = boto3.Session(
        aws_access_key_id=conf.get("aws_access_key_id"),
        aws_secret_access_key=conf.get("aws_secret_access_key"),
    )
    return session.resource("s3")


def read_conf():
    cf = "/etc/ooni/api-uploader.conf"
    log.info(f"Starting. Reading {cf}")
    conf = ConfigParser()
    conf.read(cf)
    return conf["DEFAULT"]


def ping_db(conn):
    q = "SELECT pg_postmaster_start_time();"
    with conn.cursor() as cur:
        cur.execute(q)
        row = cur.fetchone()
        log.debug("Database start time: %s", row[0])


# FIXME: move to ClickHouse
def connect_to_db(conf):
    log.info("Connecting to database")
    db_uri = conf.get(
        "db_uri", "postgresql://shovel:yEqgNr2eXvgG255iEBxVeP@localhost/metadb"
    )
    conn = psycopg2.connect(db_uri)
    return conn


@metrics.timer("update_db_table")
def update_db_table(conn, lookup_list, jsonl_s3path):
    rows = [
        (rid, inp, jsonl_s3path, num, msmt_uid)
        for rid, inp, msmt_uid, num in lookup_list
    ]
    q = "INSERT INTO jsonl (report_id, input, s3path, linenum, measurement_uid) VALUES %s"
    log.info("Writing to DB")
    with conn.cursor() as cur:
        execute_values(cur, q, rows)
        conn.commit()


@metrics.timer("upload_measurement")
def upload_to_s3(s3, bucket_name, tarf, s3path):
    obj = s3.Object(bucket_name, s3path)
    log.info(f"Uploading {s3path}")
    obj.put(Body=tarf.read_bytes())


@metrics.timer("fill_postcan")
def fill_postcan(hourdir, postcanf):
    msmt_files = sorted(f for f in hourdir.iterdir() if f.suffix == ".post")
    if not msmt_files:
        log.info(f"Nothing to fill {postcanf.name}")
        return []
    log.info(f"Filling {postcanf.name}")
    measurements = []
    postcan_byte_thresh = 20 * 1000 * 1000
    # Open postcan
    with tarfile.open(str(postcanf), "w") as tar:
        for msmt_f in msmt_files:
            # Add a msmt and delete the msmt file
            metrics.incr("msmt_count")
            tar.add(str(msmt_f))
            measurements.append(msmt_f)
            tarsize = postcanf.stat().st_size
            if tarsize > postcan_byte_thresh:
                log.info(f"Reached {tarsize} bytes")
                return measurements

    return measurements


@metrics.timer("fill_jsonl")
def fill_jsonl(measurements, jsonlf):
    log.info(f"Filling {jsonlf.name}")
    # report_id, input, 2020092119_IT_tor.n0.0.jsonl.gz
    lookup_list = []
    with gzip.open(jsonlf, "w") as jf:
        for linenum, msmt_f in enumerate(measurements):
            try:
                post = ujson.load(msmt_f.open())
            except Exception:
                log.error("Unable to parse measurement")
                jf.write(b"{}\n")
                continue

            fmt = post.get("format", "").lower()
            msm = None
            if fmt == "json":
                msm = post.get("content", {})
            elif fmt == "yaml":
                try:
                    msm = yaml.load(msm, Loader=yaml.CLoader)
                except Exception:
                    pass

            if msm is None:
                log.error("Unable to parse measurement")
                jf.write(b"{}\n")
                continue

            jf.write(ujson.dumps(msm).encode())
            jf.write(b"\n")

            rid = msm.get("report_id", "") or ""
            input = msm.get("input", "") or ""
            msmt_uid = msmt_f.name[:-5]
            lookup_list.append((rid, input, msmt_uid, linenum))

    return lookup_list


def delete_msmt_posts(measurements):
    log.info(f"Deleting {len(measurements)} measurements")
    for msmt_f in measurements:
        msmt_f.unlink()


@metrics.timer("total_run_time")
def main():
    conf = read_conf()
    bucket_name = conf.get("bucket_name")
    spooldir = Path(conf.get("msmt_spool_dir"))
    format_char = "n"
    collector_id = conf.get("collector_id", "0")
    identity = f"{format_char}{collector_id}"
    log.info(f"Uploader {collector_id} starting")
    log.info(f"Using bucket {bucket_name} and spool {spooldir}")

    s3 = create_s3_client(conf)

    db_conn = connect_to_db(conf)

    # Scan spool directories, by age
    idir = spooldir / "incoming"
    threshold = datetime.utcnow() - timedelta(hours=1)
    for hourdir in sorted(idir.iterdir()):
        if not hourdir.is_dir() or hourdir.suffix == ".tmp":
            continue
        try:
            tstamp, cc, testname = hourdir.name.split("_")
        except Exception:
            continue
        if len(tstamp) != 10:
            continue
        hourdir_time = datetime.strptime(tstamp, "%Y%m%d%H")
        if hourdir_time > threshold:
            log.info(f"Stopping before {hourdir_time}")
            break

        ping_db(db_conn)
        log.info(f"Processing {hourdir}")
        # Split msmts across multiple postcans and jsonl files
        can_cnt = 0
        while True:
            # Compress raw POSTs into a tar.gz postcan
            postcanf = hourdir.with_suffix(f".{identity}.{can_cnt}.tar.gz")
            jsonlf = hourdir.with_suffix(f".{identity}.{can_cnt}.jsonl.gz")
            msmfiles = fill_postcan(hourdir, postcanf)
            if len(msmfiles) == 0:
                break
            # Also create jsonl file and delete msmt POSTs
            lookup_list = fill_jsonl(msmfiles, jsonlf)
            delete_msmt_posts(msmfiles)

            # Upload current postcan to S3
            postcan_s3path = (
                f"raw/{tstamp[:8]}/{tstamp[8:10]}/{cc}/{testname}/{postcanf.name}"
            )
            jsonl_s3path = (
                f"raw/{tstamp[:8]}/{tstamp[8:10]}/{cc}/{testname}/{jsonlf.name}"
            )
            if conf.get("run_mode", "") == "DESTROY_DATA":
                log.info("Testbed mode: Destroying postcans!")
            else:
                upload_to_s3(s3, bucket_name, postcanf, postcan_s3path)
                upload_to_s3(s3, bucket_name, jsonlf, jsonl_s3path)
                update_db_table(db_conn, lookup_list, jsonl_s3path)

            postcanf.unlink()
            jsonlf.unlink()

            can_cnt += 1
            metrics.incr("postcan_count")

        # Delete whole hourly directory
        for f in sorted(hourdir.iterdir()):
            f.unlink()
        hourdir.rmdir()

    log.info("Exiting")


if __name__ == "__main__":
    main()
