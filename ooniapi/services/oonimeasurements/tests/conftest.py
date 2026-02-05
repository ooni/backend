import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import jwt
import pytest
import requests
import valkey
from clickhouse_driver import Client as ClickhouseClient
from fastapi.testclient import TestClient

from oonimeasurements.common.config import Settings
from oonimeasurements.common.dependencies import get_settings
from oonimeasurements.main import create_app, setup_router

THIS_DIR = Path(__file__).parent.resolve()


@pytest.fixture
def app(db, valkey_server):
    app = create_app()

    settings_override = make_override_get_settings(
        valkey_url=valkey_server,
        clickhouse_url=db,
        jwt_encryption_key="super_secure",
        prometheus_metrics_password="super_secure",
        account_id_hashing_key="super_secure",
    )
    with patch("oonimeasurements.common.dependencies.get_settings") as mocked_gs:
        mocked_gs.return_value = settings_override()
        app.dependency_overrides[get_settings] = settings_override

        setup_router(app)
        yield app


def get_file_path(file_path: str):
    return Path(__file__).parent / file_path


@pytest.fixture(scope="session")
def maybe_download_fixtures():
    base_url = "https://ooni-data-eu-fra.s3.eu-central-1.amazonaws.com/"
    filenames = [
        "samples/analysis_web_measurement-sample.sql.gz",
        "samples/obs_web-sample.sql.gz",
        "raw/20250709/07/US/webconnectivity/2025070907_US_webconnectivity.n1.7.jsonl.gz",
        "raw/20210709/00/MY/webconnectivity/2021070900_MY_webconnectivity.n0.2.jsonl.gz",
    ]
    for fn in filenames:
        dst_path = get_file_path(f"fixtures/{fn}")
        if dst_path.exists():
            continue
        url = base_url + fn
        print(f"Downloading {url} to {dst_path}")
        r = requests.get(url)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        dst_path.write_bytes(r.content)


def is_clickhouse_running(url):
    # using ClickhouseClient as probe spams WARN messages with logger in clickhouse_driver
    time.sleep(2)
    try:
        with ClickhouseClient.from_url(url) as client:
            client.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def clickhouse_server(maybe_download_fixtures, docker_ip, docker_services):
    port = docker_services.port_for("clickhouse", 9000)
    url = "clickhouse://test:test@{}:{}".format(docker_ip, port)
    docker_services.wait_until_responsive(
        timeout=30.0, pause=1.0, check=lambda: is_clickhouse_running(url)
    )
    yield url


def is_valkey_running(url):
    time.sleep(2)
    try:
        conn = valkey.from_url(url)
        conn.ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def valkey_server(docker_ip, docker_services):
    port = docker_services.port_for("valkey", 6379)
    url = f"valkey://localhost:{port}"
    docker_services.wait_until_responsive(
        timeout=30.0, pause=1.0, check=lambda: is_valkey_running(url)
    )
    yield url


def run_migration(path: Path, click: ClickhouseClient):
    sql_no_comment = "\n".join(
        filter(lambda x: not x.startswith("--"), path.read_text().split("\n"))
    )
    queries = sql_no_comment.split(";")
    for q in queries:
        q = q.strip()
        if not q:
            continue
        try:
            click.execute(q)
        except Exception as e:
            print(f"Error running migration {path}: {e}")
            raise


def create_db_for_fixture(conn_url):
    try:
        with ClickhouseClient.from_url(conn_url) as client:
            migrations_dir = THIS_DIR / "migrations"
            for fn in sorted(migrations_dir.iterdir()):
                migration_path = fn.resolve()
                run_migration(migration_path, click=client)
        return conn_url
    except Exception as e:
        pytest.skip("database migration failed")


@pytest.fixture(scope="session")
def db(clickhouse_server):
    yield create_db_for_fixture(conn_url=clickhouse_server)


def make_override_get_settings(**kw):
    def override_get_settings():
        return Settings(**kw)

    return override_get_settings


@pytest.fixture
def client_with_bad_settings(app):
    app.dependency_overrides[get_settings] = make_override_get_settings(
        clickhouse_url="clickhouse://badhost:9000"
    )

    client = TestClient(app)
    yield client


@pytest.fixture
def client(app):
    client = TestClient(app)
    yield client


def create_jwt(payload: dict) -> str:
    return jwt.encode(payload, "super_secure", algorithm="HS256")


def create_session_token(account_id: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "nbf": now,
        "iat": now,
        "exp": now + 10 * 86400,
        "aud": "user_auth",
        "account_id": account_id,
        "login_time": None,
        "role": role,
    }
    return create_jwt(payload)


@pytest.fixture
def client_with_user_role(client):
    jwt_token = create_session_token("0" * 16, "user")
    client.headers = {"Authorization": f"Bearer {jwt_token}"}
    yield client


@pytest.fixture
def client_with_admin_role(client):
    jwt_token = create_session_token("0" * 16, "admin")
    client.headers = {"Authorization": f"Bearer {jwt_token}"}
    yield client


@pytest.fixture
def params_since_and_until_with_two_days():
    return set_since_and_until_params(since="2024-11-01", until="2024-11-02")


@pytest.fixture
def params_since_and_until_with_ten_days():
    return set_since_and_until_params(since="2024-11-01", until="2024-11-10")


def set_since_and_until_params(since, until):
    params = {"since": since, "until": until}

    return params
