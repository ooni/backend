#!/usr/bin/env python3

"""
Backup database schema and tables to S3 without using temporary files
Compress data with zstd

Monitor with
sudo journalctl -f --identifier analysis

"""
# debdeps: postgresql-client-11 zstd

from datetime import datetime
from subprocess import Popen, PIPE

from smart_open import open as smart_open  # debdeps: python3-smart-open
from boto3 import Session as botoSession  # debdeps: python3-boto3

from analysis.metrics import setup_metrics  # debdeps: python3-statsd

log = None
metrics = setup_metrics(name="db-backup")


def run(cmd):
    log.debug("Running %r", cmd)
    p = Popen(cmd, shell=True, stdout=PIPE)
    while True:
        data = p.stdout.read(1 << 20)
        if not data:
            return
        yield data


@metrics.timer("run_backup")
def run_backup(conf, cp):
    log.info("Running PG backup")
    dbname = cp["active"]["dbname"]
    dbuser = cp["active"]["dbuser"]
    # dbpassword = cp["active"]["dbpassword"]
    # dbhost = cp["active"]["dbhost"]
    bucket_name = cp["s3bucket"]["bucket_name"]
    table_names = cp["backup"]["table_names"].split()
    tstamp = datetime.utcnow().strftime("%Y%m%d")
    transport = dict(
        session=botoSession(
            aws_access_key_id=cp["s3bucket"]["aws_access_key_id"],
            aws_secret_access_key=cp["s3bucket"]["aws_secret_access_key"],
        )
    )

    log.info("Create database and the whole schema, without data. SQL format")
    cmd = f"pg_dump -U {dbuser} {dbname} --create --schema-only"
    s3path = f"s3://{bucket_name}/pg_backup/{tstamp}/setup_db.sql"
    with metrics.timer("backup_schema"):
        with smart_open(s3path, "wb", transport_params=transport) as f:
            for chunk in run(cmd):
                f.write(chunk)

    for tbname in table_names:
        s3path = f"s3://{bucket_name}/pg_backup/{tstamp}/{tbname}.zstd"
        log.info("Dump and upload table %s", tbname)
        size = 0
        with metrics.timer(f"backup_table_{tbname}"):
            with smart_open(s3path, "wb", transport_params=transport) as f:
                cmd = f"pg_dump -U {dbuser} {dbname} --data-only -t {tbname}"
                cmd += " --format=custom --compress=0 | zstdmt -6 --stdout"
                for chunk in run(cmd):
                    size += len(chunk)
                    f.write(chunk)

        log.info("Written %d bytes", size)
        metrics.gauge(f"table.{tbname}.byte_count", size)

    log.info("PG backup completed")
