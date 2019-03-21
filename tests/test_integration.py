import os
import time
from glob import glob

import docker

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
AF_ROOT = os.path.join(REPO_ROOT, 'af')

def start_pg(client):
    pg_container = client.containers.run(
            'postgres:9.6',
            name='ootestmetadb',
            hostname='ootestmetadb',
            environment={
                'POSTGRES_USER': 'oopguser'
            },
            ports={
                '5432/tcp': 25432
            },
            detach=True
    )
    while True:
        exit_code, output = pg_container.exec_run("psql -U oopguser -c 'select 1'")
        if exit_code == 0:
            break
        time.sleep(0.5)
    return pg_container

def pg_load_fixtures(container):
    _, socket = container.exec_run(cmd="psql -U oopguser", stdin=True, socket=True)
    for fname in sorted(glob(os.path.join(AF_ROOT, 'oometa', '*.install.sql'))):
        with open(fname, 'rb') as in_file:
            socket._sock.sendall(in_file.read())

def main():
    try:
        client = docker.from_env()
        print("Starting pg container")
        pg_container = start_pg(client)
        pg_load_fixtures(pg_container)

    finally:
        print("Cleaning up")
        pg_container.remove(force=True)


if __name__ == '__main__':
    main()
