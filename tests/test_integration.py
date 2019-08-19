import unittest

import os
import sys
import time
import shutil
import psycopg2
import traceback
from datetime import datetime, timedelta
from glob import glob

import requests
import boto3
from botocore import UNSIGNED
from botocore.config import Config

import docker

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
AF_ROOT = os.path.join(REPO_ROOT, 'af')
TESTDATA_DIR = os.path.join(REPO_ROOT, 'testdata')

METADB_NAME = 'ootestmetadb'
METADB_PG_USER = 'oopguser'

def start_pg(client):
    pg_container = client.containers.run(
            'postgres:9.6',
            name=METADB_NAME,
            hostname=METADB_NAME,
            environment={
                'POSTGRES_USER': METADB_PG_USER
            },
            ports={
                '5432/tcp': 25432
            },
            detach=True
    )
    while True:
        exit_code, output = pg_container.exec_run("psql -U {} -c 'select 1'".format(METADB_PG_USER))
        if exit_code == 0:
            break
        time.sleep(0.5)
    return pg_container

def pg_install_tables(container):
    _, socket = container.exec_run(cmd="psql -U {}".format(METADB_PG_USER), stdin=True, socket=True)
    if hasattr(socket, '_sock'):
        socket = socket._sock
    for fname in sorted(glob(os.path.join(AF_ROOT, 'oometa', '*.install.sql'))):
        with open(fname, 'rb') as in_file:
            socket.sendall(in_file.read())

    time.sleep(1)
    for line in container.logs().split(b"\n"):
        if line.startswith(b"ERROR"):
            print(line)
            raise Exception("Detected error in query")

def fetch_autoclaved_bucket(dst_dir, bucket_date):
    dst_bucket_dir = os.path.join(dst_dir, bucket_date)
    if not os.path.exists(dst_bucket_dir):
        os.makedirs(dst_bucket_dir)
    client = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    resource = boto3.resource('s3', config=Config(signature_version=UNSIGNED))

    prefix = 'autoclaved/jsonl.tar.lz4/{}/'.format(bucket_date)
    paginator = client.get_paginator('list_objects')
    for result in paginator.paginate(Bucket='ooni-data', Delimiter='/', Prefix=prefix):
        for f in result.get('Contents', []):
            fkey = f.get('Key')
            dst_pathname = os.path.join(dst_bucket_dir, os.path.basename(fkey))
            print("[+] Downloading {}".format(dst_pathname))

            try:
                s = os.stat(dst_pathname)
                if s.st_size == f.get('Size'):
                    print('SKIP')
                    continue
            except Exception: # XXX maybe make this more strict. It's FileNotFoundError on py3 and OSError on py2
                pass
            resource.meta.client.download_file('ooni-data', fkey, dst_pathname)

def shovel_run(client, cmd):
    shovel_container = client.containers.run(
        'openobservatory/pipeline-shovel:latest',
        cmd,
        mem_limit='512m',
        user='{}:{}'.format(os.getuid(),os.getgid()),
        working_dir='/mnt',
        links={
            METADB_NAME: None
        },
        volumes={
            REPO_ROOT: {
                'bind': '/mnt',
                'mode': 'rw'
            }
        },
        privileged=True,
        stdout=True,
        stderr=True,
        detach=True
    )
    start_time = time.time()
    container_logs = shovel_container.logs(stream=True)
    for line in container_logs:
        sys.stdout.write(line.decode('utf8'))
        sys.stdout.flush()
    print("runtime: {}".format(time.time() - start_time))
    return shovel_container

def run_centrifugation(client, bucket_date):
    end_bucket_date = get_end_bucket_date(bucket_date)

    centrifugation_cmd = '/mnt/af/shovel/centrifugation.py --start {}T00:00:00'.format(bucket_date)
    centrifugation_cmd += ' --end {}T00:00:00'.format(end_bucket_date)
    centrifugation_cmd += " --autoclaved-root /mnt/testdata/autoclaved --postgres 'host={} user={}'".format(METADB_NAME, METADB_PG_USER)

    print("running shovel @{}: {}".format(start_time, centrifugation_cmd))
    shovel_container = shovel_run(client, centrifugation_cmd)

    return shovel_container

def download_file(url, dst_filename):
    with requests.get(url, stream=True) as r:
        with open(dst_filename+'.tmp', 'wb') as f:
            shutil.copyfileobj(r.raw, f)
    os.rename(dst_filename+'.tmp', dst_filename)
    return dst_filename

def download_report_files(dst_dir):
    textnames = [
        '2019-08-18/20190818T000012Z-IT-AS137-web_connectivity-20190818T000012Z_AS137_l8jGuIafZviOcWsjIpSNKgSDMK9UdDnx3Qdbvl73KXujCL6w58-0.2.0-probe.json',
        '2019-08-18/20190818T094637Z-IR-AS31549-web_connectivity-20190818T094639Z_AS31549_8wsmxeiEfEXhZz7Adm7aFBCB0bAYz8UYJWsCGxRzDNYirniZva-0.2.0-probe.json',
        '2019-08-18/20190818T094131Z-IR-AS31549-vanilla_tor-20190818T094132Z_AS31549_dDsgseksbdQ1sJn4Z1wDJD2Y2nHhFJa23DiyJlYTVKofPxWv5k-0.2.0-probe.json',
        '2019-08-18/20190818T081446Z-DE-AS8881-http_header_field_manipulation-20190818T081451Z_AS8881_zqlJZozB32oWWytaFyGZU0ouAyAIrEarNo1ahjwZ2xOEdF4RI9-0.2.0-probe.json'
    ]
    base_url = 'https://api.ooni.io/files/download/'
    for tn in textnames:
        url = base_url + tn
        dst_filename = os.path.join(dst_dir, os.path.basename(tn))
        print("downloading {}".format(dst_filename))
        if os.path.exists(dst_filename):
            continue
        download_file(url, dst_filename)

def pg_conn():
    return psycopg2.connect('host={} user={} port={}'.format('localhost', METADB_PG_USER, 25432))

def get_flag_counts():
    flags = {}
    with pg_conn() as conn:
        with conn.cursor() as c:
            c.execute("""select
                SUM(case when confirmed = TRUE then 1 else 0 end) as confirmed_count,
                SUM(case when confirmed IS NULL then 1 else 0 end) as unconfirmed_count,
                SUM(case when anomaly = TRUE then 1 else 0 end) as anomaly_count
                from measurement;
                """)
            row = c.fetchone()
            flags['confirmed'] = row[0]
            flags['unconfirmed'] = row[1]
            flags['anomaly'] = row[2]
    return flags

def get_end_bucket_date(start_date):
    fmt = '%Y-%m-%d'
    return (datetime.strptime(start_date, fmt) + timedelta(1)).strftime(fmt)

def run_canning_autoclaving():
    start_date = '2018-01-01'
    end_bucket_date = get_end_bucket_date(start_date)

    reports_raw_dir = os.path.join(TESTDATA_DIR, 'reports_raw')
    if not os.path.exists(reports_raw_dir):
        os.makedirs(reports_raw_dir)

    print("Downloading report files")
    download_report_files(reports_raw_dir)

    docker_client = docker.from_env()
    canning_cmd = '/mnt/af/shovel/canning.py --start {}T00:00:00'.format(start_date)
    canning_cmd+= ' --end {}T00:00:00'.format(end_bucket_date)
    canning_cmd += " --reports-raw-root /mnt/testdata/reports_raw --canned-root /mnt/testdata/canned"

    print("Running canning command")
    canning_container = shovel_run(docker_client, canning_cmd)
    canning_container.remove(force=True)

    autoclaving_cmd = '/mnt/af/shovel/autoclaving.py --start {}T00:00:00'.format(start_date)
    autoclaving_cmd += ' --end {}T00:00:00'.format(end_bucket_date)
    autoclaving_cmd += " --canned-root /mnt/testdata/canned --autoclaved-root /mnt/testdata/autoclaved --bridge-db /mnt/testdata/bridge_db.json"

    print("Running autoclaving command")
    autoclaving_container = shovel_run(docker_client, autoclaving_cmd)
    autoclaving_container.remove(force=True)


class TestFullPipeline(unittest.TestCase):
    def setUp(self):
        self.docker_client = docker.from_env()
        self.to_remove_containers = []

    def test_run_small_bucket(self):
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
        #bucket_date = '2018-05-07'
        #fetch_autoclaved_bucket(TESTDATA_DIR, bucket_date)

        print("Starting pg container")
        pg_container = start_pg(self.docker_client)
        self.to_remove_containers.append(pg_container)

        pg_install_tables(pg_container)

        print("Running canning and autoclaving")
        run_canning_autoclaving()

        shovel_container = run_centrifugation(self.docker_client, bucket_date)
        flags = get_flag_counts()
        print("flags: {}".format(flags))

        # This forces reprocessing of data
        with pg_conn() as conn:
            with conn.cursor() as c:
                c.execute('UPDATE autoclaved SET code_ver = 1')

        shovel_container = run_centrifugation(self.docker_client, bucket_date)

        new_flags = get_flag_counts()
        for k, count in flags.items():
            assert count == new_flags[k], "{} count doesn't match ({} != {})".format(
                k, count, new_flags[k]
            )

        # This forces reingestion of data
        with pg_conn() as conn:
            with conn.cursor() as c:
                c.execute("UPDATE autoclaved SET file_sha1 = digest('wat', 'sha1')")
        shovel_container = run_centrifugation(self.docker_client, bucket_date)

        flags = new_flags.copy()
        new_flags = get_flag_counts()
        for k, count in flags.items():
            assert count == new_flags[k], "{} count doesn't match ({} != {})".format(
                k, count, new_flags[k]
            )

        self.to_remove_containers.append(shovel_container)
        result = shovel_container.wait()
        self.assertEqual(
            result.get('StatusCode'),
            0
        )

    def tearDown(self):
        for container in self.to_remove_containers:
            container.remove(force=True)

if __name__ == '__main__':
    unittest.main()
