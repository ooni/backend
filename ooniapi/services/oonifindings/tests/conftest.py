from pathlib import Path
import pytest

import time
import jwt

from fastapi.testclient import TestClient
from clickhouse_driver import Client as ClickhouseClient

from oonifindings.common.config import Settings
from oonifindings.common.auth import hash_email_address
from oonifindings.common.dependencies import get_settings
from oonifindings.main import app

THIS_DIR = Path(__file__).parent.resolve()


def is_clickhouse_running(url):
    try:
        with ClickhouseClient.from_url(url) as client:
            client.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def clickhouse_server(docker_ip, docker_services):
    port = docker_services.port_for("clickhouse", 9000)
    url = "clickhouse://{}:{}".format(docker_ip, port)
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1, check=lambda: is_clickhouse_running(url)
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
        click.execute(q)


def create_db_for_fixture(conn_url):
    try:
        with ClickhouseClient.from_url(conn_url) as client:
            migrations_dir = THIS_DIR / "migrations"
            for fn in migrations_dir.iterdir():
                migration_path = fn.resolve()
                run_migration(migration_path, click=client)
        return conn_url
    except Exception:
        pytest.skip("database migration failed")


@pytest.fixture(scope="session")
def db(clickhouse_server):
    yield create_db_for_fixture(conn_url=clickhouse_server)


def make_override_get_settings(**kw):
    def override_get_settings():
        return Settings(**kw)

    return override_get_settings


@pytest.fixture
def client_with_bad_settings():
    app.dependency_overrides[get_settings] = make_override_get_settings(
        clickhouse_url = "clickhouse://badhost:9000"
    )

    client = TestClient(app)
    yield client


@pytest.fixture
def client(db):
    app.dependency_overrides[get_settings] = make_override_get_settings(
        clickhouse_url=db,
        jwt_encryption_key="super_secure",
        prometheus_metrics_password="super_secure",
        account_id_hashing_key="super_secure"
    )

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
    client = TestClient(app)
    jwt_token = create_session_token("0" * 16, "user")
    client.headers = {"Authorization": f"Bearer {jwt_token}"}
    yield client


@pytest.fixture
def client_with_admin_role(client):
    client = TestClient(app)
    jwt_token = create_session_token("0" * 16, "admin")
    client.headers = {"Authorization": f"Bearer {jwt_token}"}
    yield client


@pytest.fixture
def client_with_hashed_email(client):
    
    def _hashed_email(email: str, role: str):
        client = TestClient(app)
        account_id = hash_email_address(email, "super_secure")
        jwt_token = create_session_token(account_id, role)
        client.headers = {"Authorization": f"Bearer {jwt_token}"}
        return client

    return _hashed_email
