from pathlib import Path
import pytest

import time
import jwt

from fastapi.testclient import TestClient
from clickhouse_driver import Client as Clickhouse

from oonifindings.common.config import Settings
from oonifindings.common.dependencies import get_settings
from oonifindings.main import app


def run_migration(path: Path, click: Clickhouse):
    sql_no_comment = "\n".join(
        filter(lambda x: not x.startswith("--"), path.read_text().split("\n"))
    )
    queries = sql_no_comment.split(";")
    for q in queries:
        q = q.strip()
        if not q:
            continue
        click.execute(q)


@pytest.fixture
def clickhouse_migration(clickhouse):
    migrations_path = (Path(__file__).parent.parent / "migrations").resolve()

    db_url = f"clickhouse://{clickhouse.connection.host}:{clickhouse.connection.port}"

    for fn in migrations_path.iterdir():
        sql_file = fn.resolve()
        run_migration(sql_file, clickhouse)
    
    yield db_url
 

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
def client(clickhouse_migration):
    app.dependency_overrides[get_settings] = make_override_get_settings(
        clickhouse_url=clickhouse_migration,
        jwt_encryption_key="super_secure",
        prometheus_metrics_password="super_secure"
    )

    client = TestClient(app)
    yield(client)


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
