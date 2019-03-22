import os
import sys
import time
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

    shovel_container = client.containers.run(
        'openobservatory/pipeline-shovel:latest',
        centrifugation_cmd,
        mem_limit='512m',
        user='{}:{}'.format(os.getuid(),os.getgid()),
        privileged=True,
        working_dir='/mnt',
        links={
            METADB_NAME: None
        },
        volumes={
            REPO_ROOT: {
                'bind': '/mnt',
                'mode': 'rw'
            }
        }
    )
    return shovel_container

def main():
    bucket_date = '2018-01-01'

    docker_client = docker.from_env()

    fetch_autoclaved_bucket(TESTDATA_DIR, bucket_date)

    try:
        print("Starting pg container")
        pg_container = start_pg(docker_client)
        pg_install_tables(pg_container)

        print("Running centrifugation in shovel")
        start_time = time.time()
        shovel_container = run_centrifugation(docker_client, bucket_date)
        print("Runtime: {}".format(time.time() - start_time)
    except Exception as exc:
        print("Failure ", exc)
    finally:
        print("Cleaning up")
        pg_container.remove(force=True)
        shovel_container.remove(force=True)

if __name__ == '__main__':
    main()
