#!/usr/bin/env python3
"""
A hybrid between fastpath and the ooni_api_uploader.py from the API
To be used once, fetches legacy cans from the legacy S3 bucket
Generates new postcans and jsonl files and uploads to the new S3 bucket
Updates both the fastpath and jsonl tables

Inputs:
  Legacy raw cans in old S3 bucket

Outputs:
  jsonl files in new S3 bucket e.g.:
    jsonl/{testname}/{cc}/{ts}/00/{jsonlf.name}
  rows in the jsonl database table
    upsert or insert-but-not-overwrite

Usage:
export AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
PYTHONPATH=. ./fastpath/reprocessor.py ooni-data ooni-data-eu-fra-test --day 2015-1-1

DB update:

BEGIN;
ALTER TABLE jsonl ADD COLUMN measurement_uid TEXT;
COMMIT;
CREATE UNIQUE INDEX CONCURRENTLY jsonl_unique ON jsonl (report_id, input, measurement_uid);
DROP INDEX IF EXISTS jsonl_lookup_idx;
ALTER TABLE jsonl DROP COLUMN id;
"""

from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime
from os import getenv
from pathlib import Path
import gzip
import logging
import os

import ujson
import psycopg2  # debdeps: python3-psycopg2
from psycopg2.extras import execute_values
import statsd  # debdeps: python3-statsd

import fastpath.db as db
import fastpath.s3feeder as s3f
from fastpath.core import score_measurement, setup_fingerprints, unwrap_msmt
from fastpath.core import trivial_id

metrics = statsd.StatsClient("127.0.0.1", 8125, prefix="reprocessor")
log = logging.getLogger("reprocessor")
log.addHandler(logging.StreamHandler())  # Writes to console
log.setLevel(logging.DEBUG)
for lo in ("urllib3", "botocore", "s3transfer", "boto"):
    logging.getLogger(lo).setLevel(logging.INFO)


import boto3


def create_s3_client(conf):
    session = boto3.Session(
        aws_access_key_id=getenv("aws_access_key_id"),
        aws_secret_access_key=getenv("aws_secret_access_key"),
    )
    return session.resource("s3")


def ping_db(conn):
    q = "SELECT pg_postmaster_start_time();"
    with conn.cursor() as cur:
        cur.execute(q)
        row = cur.fetchone()
        log.debug("Database start time: %s", row[0])


def update_db_table(conn, lookup_list, jsonltbl_policy):
    if jsonltbl_policy == "dryrun":
        return

    q = """INSERT INTO jsonl
    (report_id, input, measurement_uid, s3path, linenum) VALUES %s
    ON CONFLICT (report_id, input, measurement_uid) DO
    """
    if jsonltbl_policy == "upsert":
        log.info(f"Upserting {len(lookup_list)} rows to DB")
        q += "UPDATE SET s3path = excluded.s3path, linenum = excluded.linenum"
    elif jsonltbl_policy == "insert":
        log.info(f"Inserting {len(lookup_list)} rows to DB")
        q += "NOTHING"
    else:
        raise Exception(f"Unexpected --jsonltbl value {jsonltbl_policy}")

    with conn.cursor() as cur:
        execute_values(cur, q, lookup_list)
        conn.commit()


@metrics.timer("upload_measurement")
def upload_to_s3(s3, bucket_name, tarf, s3path):
    obj = s3.Object(bucket_name, s3path)
    log.info(f"Uploading {tarf} to {s3path}")
    obj.put(Body=tarf.read_bytes())


def parse_date(d):
    return datetime.strptime(d, "%Y-%m-%d").date()


def parse_args():
    os.environ["TZ"] = "UTC"
    ap = ArgumentParser(__doc__)
    ap.add_argument("src_bucket")
    ap.add_argument("dst_bucket")
    ap.add_argument("--day", type=lambda d: parse_date(d))
    ap.add_argument(
        "--jsonltbl",
        choices=["dryrun", "insert", "upsert"],
        default="upsert",
        help="jsonl table update policy. insert = never overwrite",
    )
    ap.add_argument(
        "--fastpathtbl",
        choices=["dryrun", "insert", "upsert"],
        default="upsert",
        help="fastpath table update policy. insert = never overwrite",
    )
    db = "postgresql://shovel:yEqgNr2eXvgG255iEBxVeP@localhost/metadb"
    ap.add_argument("--db-uri", default=db)
    c = ap.parse_args()

    return c


def score_measurement_and_upsert_fastpath(msm, msmt_uid, do_update: bool) -> None:
    scores = score_measurement(msm)
    anomaly = scores.get("blocking_general", 0.0) > 0.5
    failure = scores.get("accuracy", 1.0) < 0.5
    confirmed = scores.get("confirmed", False)

    sw_name = msm.get("software_name", "unknown")
    sw_version = msm.get("software_version", "unknown")
    platform = "unset"
    if "annotations" in msm and isinstance(msm["annotations"], dict):
        platform = msm["annotations"].get("platform", "unset")

    db.upsert_summary(
        msm,
        scores,
        anomaly,
        confirmed,
        failure,
        msmt_uid,
        sw_name,
        sw_version,
        platform,
        do_update,
    )


@dataclass
class Entity:
    jsonlf: Path
    fd: int
    jsonl_s3path: str
    lookup_list: list


def finalize_jsonl(s3sig, db_conn, conf, e: Entity) -> None:
    jsize = int(e.fd.offset / 1024)
    log.info(f"Closing jsonl and uploading it. Size: {jsize} KB")
    e.fd.close()
    upload_to_s3(s3sig, conf.dst_bucket, e.jsonlf, e.jsonl_s3path)
    update_db_table(db_conn, e.lookup_list, conf.jsonltbl)
    e.jsonlf.unlink()


def process_measurement(msm_tup, buf, seen_uids, conf, s3sig, db_conn):
    """Process a msmt
    If needed: create a new Entity tracking a jsonl file,
      close and upload jsonl to S3 and upsert db
    """
    THRESHOLD = 20 * 1024 * 1024
    msm_jstr, msm, _ = msm_tup
    assert msm is None
    if msm is None:
        msm = ujson.loads(msm_jstr)
    if sorted(msm.keys()) == ["content", "format"]:
        msm = unwrap_msmt(msm)

    msmt_uid = trivial_id(msm)
    rid = msm.get("report_id", None)
    inp = msm.get("input", None)
    tn = msm.get("test_name").replace("_", "")
    cc = msm.get("probe_cc").upper()
    # if msmt_uid == "00c11116832b22cb75a6fc8868c72b72":
    #    log.debug(f"Processing {msmt_uid} {tn} {cc} {rid} {inp}")
    #    Path("meow").write_text(ujson.dumps(msm, sort_keys=1, indent=1))

    # log.debug(f"Processing {msmt_uid} {tn} {cc} {rid} {inp}")
    if msmt_uid in seen_uids:
        log.info(f"DUPLICATE {msmt_uid} {tn} {cc} {rid} {inp}")
        return
        # Path("meow2").write_text(ujson.dumps(msm, sort_keys=1, indent=1))
        # sys.exit(1)
    seen_uids.add(msmt_uid)

    if msm.get("probe_cc", "").upper() == "ZZ":
        log.debug("Ignoring measurement with probe_cc=ZZ")
        metrics.incr("discarded_measurement")
        return

    if msm.get("probe_asn", "").upper() == "AS0":
        log.debug("Ignoring measurement with ASN 0")
        metrics.incr("discarded_measurement")
        return

    # cc tn -> [entity1, entity2, ... ]

    entities = buf.setdefault(f"{cc} {tn}", [])
    if len(entities) == 0 or entities[-1].fd.closed:
        ts = conf.day.strftime("%Y%m%d")
        jsonlf = Path(f"{ts}_{cc}_{tn}.l.{len(entities)}.jsonl.gz")
        jsonl_s3path = f"jsonl/{tn}/{cc}/{ts}/00/{jsonlf.name}"
        e = Entity(
            jsonlf=jsonlf,
            fd=gzip.open(jsonlf, "w"),
            jsonl_s3path=jsonl_s3path,
            lookup_list=[],
        )
        entities.append(e)

    e = entities[-1]

    # Add msmt to open jsonl file
    e.fd.write(ujson.dumps(msm).encode())
    e.fd.write(b"\n")

    rid = msm.get("report_id", "") or ""
    input = msm.get("input", "") or ""
    i = (rid, input, msmt_uid, str(e.jsonl_s3path), len(e.lookup_list))
    e.lookup_list.append(i)

    if e.fd.offset > THRESHOLD:
        # The jsonlf is big enough
        finalize_jsonl(s3sig, db_conn, conf, e)

    if conf.fastpathtbl in ("insert", "upsert"):
        update = conf.fastpathtbl == "upsert"
        score_measurement_and_upsert_fastpath(msm, msmt_uid, update)


@metrics.timer("total_run_time")
def main():
    conf = parse_args()
    format_char = "n"
    collector_id = "L"
    identity = f"{format_char}{collector_id}"
    log.info(f"From bucket {conf.src_bucket} to {conf.dst_bucket}")
    s3sig = create_s3_client(conf)  # signed client for writing
    db_conn = psycopg2.connect(conf.db_uri)
    db.setup(conf)  # setup db conn inside db module
    setup_fingerprints()

    # Fetch msmts for one day

    buf = {}  # "<cc> <testname>" -> jsonlf / fd / jsonl_s3path
    seen_uids = set()  # Avoid uploading duplicates

    # raw/20210601/00/SA/webconnectivity/2021060100_SA_webconnectivity.n0.0.jsonl.gz
    # jsonl_s3path = f"raw/{ts}/00/{cc}/{testname}/{jsonlf.name}"

    s3uns = s3f.create_s3_client()  # unsigned client for reading
    cans_fns = s3f.list_cans_on_s3_for_a_day(s3uns, conf.day)
    cans_fns = sorted(cans_fns)  # this is not enough to sort by time
    tot_size = sum(size for _, size in cans_fns)
    processed_size = 0
    log.info(f"{tot_size/1024/1024/1024} GB to process")
    log.info(f"{len(cans_fns)} cans to process")
    #  TODO make assertions on msmt
    #  TODO add consistency check on trivial id found in fastpath table
    for can in cans_fns:
        can_fn, size = can
        log.info(f"Processed percentage: {100 * processed_size / tot_size}")
        log.info(f"Opening can {can_fn}")
        Path(can_fn).parent.mkdir(parents=True, exist_ok=True)
        s3uns.download_file(conf.src_bucket, can_fn, can_fn)
        for msm_tup in s3f.load_multiple(can_fn):
            process_measurement(msm_tup, buf, seen_uids, conf, s3sig, db_conn)
        processed_size += size

    log.info("Finish jsonl files still open")
    for json_entities in buf.values():
        for e in json_entities:
            if e.fd.closed:
                continue
            finalize_jsonl(s3sig, db_conn, conf, e)

    log.info("Exiting")


if __name__ == "__main__":
    main()
