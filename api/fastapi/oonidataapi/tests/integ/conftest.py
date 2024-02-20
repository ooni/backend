from pathlib import Path
import time
from fastapi.testclient import TestClient
import pytest
import docker
from docker.models.containers import Container as DockerContainer

from clickhouse_driver import Client as Clickhouse

from ...config import settings
from ...main import app

THIS_DIR = Path(__file__).parent


def pytest_addoption(parser):
    parser.addoption("--proddb", action="store_true", help="uses data from prod DB")


def pytest_configure(config):
    pytest.proddb = config.getoption("--proddb")


def run_clickhouse_sql_scripts(clickhouse_url):
    click = Clickhouse.from_url(clickhouse_url)
    tables = click.execute("SHOW TABLES")
    for row in tables:
        if row[0] == "fastpath":
            return

    for fn in ["1_schema", "2_fixtures"]:
        sql_f = THIS_DIR / f"clickhouse_{fn}.sql"
        print(f"[+] running {sql_f} on {clickhouse_url}")
        sql_no_comment = "\n".join(
            filter(lambda x: not x.startswith("--"), sql_f.read_text().split("\n"))
        )
        queries = sql_no_comment.split(";")
        for q in queries:
            q = q.strip()
            if not q:
                continue
            click.execute(q)


@pytest.fixture(autouse=True, scope="session")
def clickhouse(docker_clickhouse_url):
    settings.clickhouse_url = docker_clickhouse_url
    run_clickhouse_sql_scripts(settings.clickhouse_url)
    return docker_clickhouse_url


@pytest.fixture(scope="session")
def docker_clickhouse_url():
    client = docker.from_env()
    image_name = "yandex/clickhouse-server:21.8-alpine"
    print(f"\n[+] pulling clickhouse image from {image_name}")
    client.images.pull(image_name)
    # Run a container with a random port mapping for ClickHouse default port 9000
    container = client.containers.run(
        image_name,
        ports={
            "9000/tcp": None
        },  # This maps port 9000 inside the container to a random host port
        detach=True,
    )
    assert isinstance(container, DockerContainer)

    # Wait for the container to be ready
    time.sleep(10)

    # Obtain the port mapping
    container.reload()
    assert isinstance(container.attrs, dict)
    host_port = container.attrs["NetworkSettings"]["Ports"]["9000/tcp"][0]["HostPort"]

    # Construct the connection string
    connection_string = f"clickhouse://localhost:{host_port}"

    yield connection_string

    # Cleanup after the test session is done
    container.stop()
    container.remove()


@pytest.yield_fixture
def client():
    """
    Overriding the `client` fixture from pytest_flask to fix this bug:
    https://github.com/pytest-dev/pytest-flask/issues/42
    """
    client = TestClient(app)
    yield client
