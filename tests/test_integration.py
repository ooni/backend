import unittest

import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from glob import glob

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

def run_centrifugation(client, bucket_date):
    fmt = '%Y-%m-%d'
    end_bucket_date = (datetime.strptime(bucket_date, fmt) + timedelta(1)).strftime(fmt)

    centrifugation_cmd = '/mnt/af/shovel/centrifugation.py --start {}T00:00:00'.format(bucket_date)
    centrifugation_cmd += ' --end {}T00:00:00'.format(end_bucket_date)
    centrifugation_cmd += " --autoclaved-root /mnt/testdata --postgres 'host={} user={}'".format(METADB_NAME, METADB_PG_USER)

    start_time = time.time()

    print("running shovel @{}: {}".format(start_time, centrifugation_cmd))
    shovel_container = client.containers.run(
        'openobservatory/pipeline-shovel:latest',
        centrifugation_cmd,
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
    container_logs = shovel_container.logs(stream=True)
    for line in container_logs:
        sys.stdout.write(line.decode('utf8'))
        sys.stdout.flush()
    print("runtime: {}".format(time.time() - start_time))
    return shovel_container

class TestCentrifugation(unittest.TestCase):
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
        bucket_date = '2019-03-01'
        fetch_autoclaved_bucket(TESTDATA_DIR, bucket_date)

        print("Starting pg container")
        pg_container = start_pg(self.docker_client)
        self.to_remove_containers.append(pg_container)

        pg_install_tables(pg_container)

        shovel_container = run_centrifugation(self.docker_client, bucket_date)
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
