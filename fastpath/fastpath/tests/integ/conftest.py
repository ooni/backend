import pytest
import requests
from clickhouse_driver.client import Client as ClickhouseClient


@pytest.fixture(scope="session")
def clickhouse_server(docker_ip, docker_services):
    port = docker_services.port_for("clickhouse", 9000)
    url = "clickhouse://test:test@{}:{}".format(docker_ip, port)
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1, check=lambda: is_clickhouse_running(url)
    )
    yield url

@pytest.fixture(scope="session")
def fastpath_service(docker_ip, docker_services):
    port = docker_services.port_for("fastpath", 8472)
    url = f"http://{docker_ip}:{port}"
    docker_services.wait_until_responsive(
        timeout=20, pause=0.1, check=lambda: is_fastpath_running(url)
    )

    yield url

def is_fastpath_running(url : str) -> bool: 
    print("checking if fastpath is running...")
    try: 
        req = requests.get(url)
        assert req.status_code == 200
        return True
    except Exception:
        return False

def is_clickhouse_running(url):
    try:
        with ClickhouseClient.from_url(url) as client:
            client.execute("SELECT 1")
        return True
    except Exception:
        return False
