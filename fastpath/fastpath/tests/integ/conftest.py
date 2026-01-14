import pytest
import requests
from clickhouse_driver.client import Client as ClickhouseClient
import os 

# Time to wait for docker services
TIMEOUT = 10.0

@pytest.fixture(scope="session")
def clickhouse_service(docker_ip, docker_services):
    port = docker_services.port_for("clickhouse-server", 9000)
    url = "clickhouse://default:default@{}:{}".format(docker_ip, port)
    docker_services.wait_until_responsive(
        timeout=TIMEOUT, pause=0.1, check=lambda: is_clickhouse_running(url)
    )
    yield url

@pytest.fixture(scope="session")
def fastpath_service(docker_ip, docker_services, clickhouse_service):
    port = docker_services.port_for("fastpath", 8472)
    url = f"http://{docker_ip}:{port}"
    docker_services.wait_until_responsive(
        timeout=TIMEOUT, pause=0.1, check=lambda: is_fastpath_running(url)
    )

    yield url

def is_fastpath_running(url : str) -> bool: 
    print("checking if fastpath is running...")
    try: 
        req = requests.get(url)
        return req.status_code == 200
    except Exception:
        return False

def is_clickhouse_running(url):
    try:
        with ClickhouseClient.from_url(url) as client:
            client.execute("SELECT 1")
        return True
    except Exception:
        return False

@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    # Fastpath has a weird file layout, causing 
    # the docker plugin to generate the wrong docker-compose.yml path
    # This line will make sure that the tests run properly with make 
    return os.path.join(str(pytestconfig.rootdir), "fastpath", "tests", "docker-compose.yml")
