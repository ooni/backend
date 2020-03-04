"""
Run integration test

Run with tox using: `tox`
Help: `tox -- -h`
Run against a shovel image tag: `tox -- --shovel-image-tag 20190704-4659f159`
"""

import json
import errno
import os
import psycopg2
import random
import shutil
import string
import sys
import time
from datetime import datetime, timedelta
from glob import glob

from botocore import UNSIGNED
from botocore.config import Config
from pytest import fixture
import boto3
import requests

import docker

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AF_ROOT = os.path.join(REPO_ROOT, "af")
TESTDATA_DIR = os.path.join(REPO_ROOT, "testdata")

METADB_NAME = "ootestmetadb"
METADB_PG_USER = "oopguser"
PG_EXT_PORT = 25432


@fixture
def pg_container(docker_client):
    ## Start Postgres in a dedicated container named in METADB_NAME
    pg_container = docker_client.containers.run(
        "postgres:9.6",
        name=METADB_NAME,
        hostname=METADB_NAME,
        environment={"POSTGRES_USER": METADB_PG_USER, "POSTGRES_PASSWORD": METADB_PG_USER},
        ports={"5432/tcp": PG_EXT_PORT},
        detach=True,
    )
    # TODO ensure this doesn't run into an infinite loop, though it hasn't been a problem up until now.
    while True:
        exit_code, output = pg_container.exec_run(
            "psql -U {} -c 'select 1'".format(METADB_PG_USER),
            environment={"PGPASSWORD": METADB_PG_USER}
        )
        if exit_code == 0:
            break
        time.sleep(0.5)

    print("Starting pg container")
    pg_install_tables(pg_container)

    yield pg_container

    pg_container.remove(force=True)


def pg_install_tables(container):
    _, socket = container.exec_run(
        cmd="psql -U {}".format(METADB_PG_USER), stdin=True, socket=True,
        environment={"PGPASSWORD": METADB_PG_USER}
    )
    # This is to support multiple versions of docker and python.
    # See: https://github.com/docker/docker-py/issues/2255#issuecomment-475270012
    if hasattr(socket, "_sock"):
        socket = socket._sock
    for fname in sorted(glob(os.path.join(AF_ROOT, "oometa", "*.install.sql"))):
        with open(fname, "rb") as in_file:
            socket.sendall(in_file.read())

    time.sleep(1)
    for line in container.logs().split(b"\n"):
        if line.startswith(b"ERROR"):
            print(line)
            raise Exception("Detected error in query")


def fetch_autoclaved_bucket(dst_dir, bucket_date):
    print("Fetch bucket")
    dst_bucket_dir = os.path.join(dst_dir, bucket_date)
    if not os.path.exists(dst_bucket_dir):
        os.makedirs(dst_bucket_dir)
    client = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    resource = boto3.resource("s3", config=Config(signature_version=UNSIGNED))

    prefix = "autoclaved/jsonl.tar.lz4/{}/".format(bucket_date)
    paginator = client.get_paginator("list_objects")
    for result in paginator.paginate(Bucket="ooni-data", Delimiter="/", Prefix=prefix):
        for f in result.get("Contents", []):
            fkey = f.get("Key")
            dst_pathname = os.path.join(dst_bucket_dir, os.path.basename(fkey))
            try:
                s = os.stat(dst_pathname)
                if s.st_size == f.get("Size"):
                    continue
            except Exception:  # XXX maybe make this more strict. It's FileNotFoundError on py3 and OSError on py2
                pass
            print("[+] Downloading {}".format(dst_pathname))
            resource.meta.client.download_file("ooni-data", fkey, dst_pathname)


def shovel_run(client, cmd, pipeline_ctx):
    shovel_container = client.containers.run(
        "openobservatory/pipeline-shovel:latest",
        cmd,
        mem_limit="512m",
        user="{}:{}".format(os.getuid(), os.getgid()),
        working_dir="/mnt",
        links={METADB_NAME: None},
        volumes={
            pipeline_ctx['working_dir_root']: {"bind": "/data", "mode": "rw"},
            REPO_ROOT: {"bind": "/mnt", "mode": "rw"}
        },
        privileged=True,
        stdout=True,
        stderr=True,
        detach=True,
    )
    start_time = time.time()
    container_logs = shovel_container.logs(stream=True)
    for line in container_logs:
        sys.stdout.write(line.decode("utf8"))
        sys.stdout.flush()
    print("runtime: {}".format(time.time() - start_time))
    return shovel_container


def run_centrifugation(client, bucket_date, pipeline_ctx):
    ## Run centrifugation in a dedicated container based on
    ## the openobservatory/pipeline-shovel:latest image
    end_bucket_date = get_end_bucket_date(bucket_date)

    centrifugation_cmd = "/mnt/af/shovel/centrifugation.py --start {}T00:00:00".format(
        bucket_date
    )
    centrifugation_cmd += " --end {}T00:00:00".format(end_bucket_date)
    centrifugation_cmd += " --autoclaved-root /data/autoclaved --postgres 'host={} user={} password={}'".format(
        METADB_NAME, METADB_PG_USER, METADB_PG_USER
    )

    print("running shovel: {}".format(centrifugation_cmd))
    shovel_container = shovel_run(client, centrifugation_cmd, pipeline_ctx)

    return shovel_container


def download_file(url, dst_filename):
    with requests.get(url, stream=True) as r:
        with open(dst_filename + ".tmp", "wb") as f:
            shutil.copyfileobj(r.raw, f)
    os.rename(dst_filename + ".tmp", dst_filename)
    return dst_filename


def download_report_files(dst_dir):
    textnames = [
        "2019-06-01/20190601T003644Z-IN-AS18196-web_connectivity-20190601T003645Z_AS18196_rpEBAw2sJIRwgKvm3JhOur2dNqOdtIb0ktIywHC3KAfXBgPik6-0.2.0-probe.json",
        "2019-08-18/20190818T094131Z-IR-AS31549-vanilla_tor-20190818T094132Z_AS31549_dDsgseksbdQ1sJn4Z1wDJD2Y2nHhFJa23DiyJlYTVKofPxWv5k-0.2.0-probe.json",
        "2019-08-18/20190818T081446Z-DE-AS8881-http_header_field_manipulation-20190818T081451Z_AS8881_zqlJZozB32oWWytaFyGZU0ouAyAIrEarNo1ahjwZ2xOEdF4RI9-0.2.0-probe.json",
    ]
    base_url = "https://api.ooni.io/files/download/"
    for tn in textnames:
        url = base_url + tn
        dst_filename = os.path.join(dst_dir, os.path.basename(tn))
        print("downloading {}".format(dst_filename))
        if os.path.exists(dst_filename):
            continue
        download_file(url, dst_filename)

def generate_report_files(dst_dir):
    sample_fname = "20190601T003644Z-IN-AS18196-web_connectivity-20190601T003645Z_AS18196_rpEBAw2sJIRwgKvm3JhOur2dNqOdtIb0ktIywHC3KAfXBgPik6-0.2.0-probe.json"

    now = datetime.now() - timedelta(days=2)
    isostamp = now.strftime("%Y%m%dT010203Z")
    report_id = "{}_AS18196_rpEBAw2sJIRwgKvm3JhOur2dNqOdtIb0ktIywHC3KAfXBgPik6".format(isostamp)

    gen_fname = '{}-IN-AS18196-web_connectivity-{}-0.2.0-probe.json'.format(isostamp, report_id)

    with open(os.path.join(dst_dir, sample_fname)) as in_file:
        j = json.loads(in_file.readline())

    # We generate a report file with the time of today so that the ooexpl_
    # metrics will get computed on this as it will be a recent measurement
    measurement_start_time = now.strftime("%Y-%m-%d %H:%M:%S")
    j['report_id'] = report_id
    j['test_start_time'] = measurement_start_time
    j['measurement_start_time'] = measurement_start_time
    j['report_filename'] = os.path.join('2018-01-01', gen_fname)
    j['id'] = 'deadbeef-dead-beef-8ad8-ca2dbc56bca5'

    with open(os.path.join(dst_dir, gen_fname), 'w') as out_file:
        json.dump(j, out_file)
        out_file.write('\n') # the autoclaving process expects there to be a newline

def pg_conn():
    return psycopg2.connect(
        "host={} user={} password={} port={}".format("localhost", METADB_PG_USER, METADB_PG_USER, PG_EXT_PORT)
    )


def get_flag_counts():
    flags = {}
    with pg_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                """select
                SUM(case when confirmed = TRUE then 1 else 0 end) as confirmed_count,
                SUM(case when confirmed IS NULL then 1 else 0 end) as unconfirmed_count,
                SUM(case when anomaly = TRUE then 1 else 0 end) as anomaly_count
                from measurement;
                """
            )
            row = c.fetchone()
            flags["confirmed"] = row[0]
            flags["unconfirmed"] = row[1]
            flags["anomaly"] = row[2]
    return flags


def get_end_bucket_date(start_date):
    fmt = "%Y-%m-%d"
    return (datetime.strptime(start_date, fmt) + timedelta(1)).strftime(fmt)

def run_canning_autoclaving(pipeline_ctx):
    start_date = "2018-01-01"
    end_bucket_date = get_end_bucket_date(start_date)

    print("Downloading report files")
    reports_raw_dir = os.path.join(pipeline_ctx['reports_raw'], start_date)
    for dn in ['reports_raw', 'canned', 'autoclaved']:
        path = os.path.join(pipeline_ctx[dn], start_date)
        if not os.path.exists(path):
            os.makedirs(path)
    download_report_files(reports_raw_dir)
    generate_report_files(reports_raw_dir)

    docker_client = docker.from_env()
    canning_cmd = "/mnt/af/shovel/canning.py --start {}T00:00:00".format(start_date)
    canning_cmd += " --end {}T00:00:00".format(end_bucket_date)
    canning_cmd += " --reports-raw-root /mnt/testdata/reports_raw --canned-root /data/canned"

    print("Running canning command")
    canning_container = shovel_run(docker_client, canning_cmd, pipeline_ctx)
    canning_container.remove(force=True)

    autoclaving_cmd = "/mnt/af/shovel/autoclaving.py --start {}T00:00:00".format(
        start_date
    )
    autoclaving_cmd += " --end {}T00:00:00".format(end_bucket_date)
    autoclaving_cmd += " --canned-root /data/canned --autoclaved-root /data/autoclaved --bridge-db /mnt/testdata/bridge_db.json"

    print("Running autoclaving command")
    autoclaving_container = shovel_run(docker_client, autoclaving_cmd, pipeline_ctx)
    autoclaving_container.remove(force=True)

@fixture
def docker_client():
    yield docker.from_env()

def randStr(length):
    letters = string.ascii_letters
    return ''.join(random.choice(letters) for i in range(length))

def rm_rf(path):
    pass

@fixture
def pipeline_dir_ctx():
    working_dir = os.path.join(TESTDATA_DIR, 'working_dir' + randStr(20))
    os.makedirs(working_dir)

    ctx = {
        'repo_root': REPO_ROOT,
        'working_dir_root': working_dir,

        'reports_raw': os.path.join(TESTDATA_DIR, "reports_raw"),
        'canned': os.path.join(working_dir, 'canned'),
        'autoclaved': os.path.join(working_dir, 'autoclaved')
    }

    with open(os.path.join(TESTDATA_DIR, "bridge_db.json"), "w") as out_file:
        out_file.write("{}")

    for dn in ['reports_raw', 'canned', 'autoclaved']:
        try:
            os.makedirs(ctx[dn])
        except OSError as e:
            if e.errno == errno.EEXIST:
                pass
            else:
                raise
    yield ctx

    shutil.rmtree(working_dir, ignore_errors=True)

def print_query_fetchone_output(conn, q):
    with conn.cursor() as c:
        c.execute(q)
        row = c.fetchone()
        print("----")
        print(q)
        print(row)
        print("----")
    return row

def test_run_small_bucket(docker_client, pg_container, pipeline_dir_ctx):
    """
    Buckets sizes for testing:
    665M	2018-05-07
    906M	2018-05-08
    700M	2018-05-09
    1.1G	2017-02-09
    1.7G	2017-04-16
    4.8G	2018-03-04
    1.3G	2019-03-01
    2.7G 2017-06-05
    60M	        2016-07-07

    Empty buckets:
    4.0K	2015-12-24
    4.0K	2015-12-25
    4.0K	2015-12-26
    4.0K	2015-12-27
    4.0K	2015-12-28
    4.0K	2018-12-09
    4.0K	2018-12-10
    """
    bucket_date = "2018-01-01"
    # bucket_date = '2018-05-07'
    # fetch_autoclaved_bucket(TESTDATA_DIR, bucket_date)

    print("Running canning and autoclaving")
    run_canning_autoclaving(pipeline_dir_ctx)

    shovel_container = run_centrifugation(docker_client, bucket_date, pipeline_dir_ctx)
    flags = get_flag_counts()
    print("flags[0]: {}".format(flags))

    with pg_conn() as conn:
        print_query_fetchone_output(conn, 'SELECT COUNT(*) FROM http_request_fp;')

    assert flags["confirmed"] == 8, "confirmed count"

    # This forces reprocessing of data
    with pg_conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE measurement SET confirmed = NULL;")
            c.execute("TRUNCATE TABLE http_request_fp;")
            c.execute("UPDATE autoclaved SET code_ver = 1;")

    flags = get_flag_counts()
    print("flags[1]: {}".format(flags))
    shovel_container = run_centrifugation(docker_client, bucket_date, pipeline_dir_ctx)
    flags = get_flag_counts()
    print("flags[2]: {}".format(flags))
    with pg_conn() as conn:
        print_query_fetchone_output(conn, 'SELECT COUNT(*) FROM http_request_fp;')
        row = print_query_fetchone_output(conn, 'SELECT COUNT(*) FROM ooexpl_wc_input_counts;')
        assert row[0] > 0, "ooexpl_wc_input_counts is empty"

    new_flags = get_flag_counts()
    for k, count in flags.items():
        assert count == new_flags[k], "{} count doesn't match ({} != {})".format(
            k, count, new_flags[k]
        )

    # This forces reingestion of data
    with pg_conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE autoclaved SET file_sha1 = digest('wat', 'sha1')")
    shovel_container = run_centrifugation(docker_client, bucket_date, pipeline_dir_ctx)

    flags = new_flags.copy()
    new_flags = get_flag_counts()
    for k, count in flags.items():
        assert count == new_flags[k], "{} count doesn't match ({} != {})".format(
            k, count, new_flags[k]
        )
    print("flags[3]: {}".format(flags))

    result = shovel_container.wait()
    assert result.get("StatusCode") == 0
    shovel_container.remove(force=True)
