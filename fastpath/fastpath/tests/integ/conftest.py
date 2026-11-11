"""
Integration tests: the fastpath image in FASTPATH_IMAGE, run as ooni/devops
runs it, against a one-node ClickHouse cluster with production's schema.

    FASTPATH_IMAGE=ooni/fastpath:<tag> pytest fastpath/tests/integ
"""

import os
import subprocess
from pathlib import Path

import pytest
import requests
from clickhouse_driver.client import Client as ClickhouseClient

HERE = Path(__file__).parent
FETCH_SCHEMA = HERE / "clickhouse" / "fetch_schema.sh"

# Seconds to wait for fastpath to answer once started
TIMEOUT = 60.0


@pytest.fixture(scope="session")
def docker_compose_file():
    return str(HERE.parent / "docker-compose.yml")


@pytest.fixture(scope="session")
def docker_setup():
    if not os.environ.get("FASTPATH_IMAGE"):
        pytest.fail("set FASTPATH_IMAGE to the fastpath image to test")
    # ClickHouse only: fastpath starts once the schema is loaded
    return ["up --wait clickhouse-server"]


@pytest.fixture(scope="session")
def docker_cleanup():
    return ["--profile fastpath down -v"]


@pytest.fixture(scope="session")
def compose(docker_compose_command, docker_compose_file, docker_compose_project_name):
    """Run a docker compose subcommand in the test project"""

    def run(*args, **kwargs):
        cmd = docker_compose_command.split() + [
            "-f", docker_compose_file, "-p", docker_compose_project_name, *args
        ]
        return subprocess.run(cmd, check=True, **kwargs)

    return run


@pytest.fixture(scope="session")
def clickhouse_service(docker_ip, docker_services, compose, tmp_path_factory):
    """ClickHouse with production's schema in the ooni database"""
    schema = tmp_path_factory.mktemp("schema") / "schema.sql"
    subprocess.run([str(FETCH_SCHEMA), str(schema)], check=True)

    def client(*args, **kwargs):
        return compose(
            "exec", "-T", "clickhouse-server",
            "clickhouse-client", "--user", "default", "--password", "default", *args,
            **kwargs,
        )

    client("-q", "CREATE DATABASE IF NOT EXISTS ooni ON CLUSTER oonidata_cluster FORMAT Null",
           stdin=subprocess.DEVNULL)
    with schema.open() as f:
        client("--database", "ooni", "--multiquery", stdin=f, stdout=subprocess.DEVNULL)

    port = docker_services.port_for("clickhouse-server", 9000)
    yield f"clickhouse://default:default@{docker_ip}:{port}/ooni"


@pytest.fixture(scope="session")
def clickhouse(clickhouse_service):
    with ClickhouseClient.from_url(clickhouse_service) as client:
        yield client


@pytest.fixture(scope="session")
def fastpath_service(docker_ip, docker_services, compose, clickhouse_service):
    compose("--profile", "fastpath", "up", "-d", "fastpath")
    port = docker_services.port_for("fastpath", 8472)
    url = f"http://{docker_ip}:{port}"
    docker_services.wait_until_responsive(
        timeout=TIMEOUT, pause=0.5, check=lambda: is_fastpath_running(url)
    )
    yield url


def is_fastpath_running(url: str) -> bool:
    try:
        return requests.get(url, timeout=2).status_code == 200
    except Exception:
        return False
