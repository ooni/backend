from pathlib import Path
import pytest

import time
import jwt

from clickhouse_driver import Client as ClickhouseClient

from fastapi.testclient import TestClient

from oonifindings.common.config import Settings
from oonifindings.common.auth import hash_email_address
from oonifindings.common.dependencies import get_settings
from oonifindings.main import app

THIS_DIR = Path(__file__).parent.resolve()


def read_file(file_path: str):
    return (Path(__file__).parent / file_path).read_text()


def is_clickhouse_running(url):
    try:
        with ClickhouseClient.from_url(url) as client:
            client.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def clickhouse_server(docker_ip, docker_services):
    """Ensure that HTTP service is up and responsive."""
    port = docker_services.port_for("clickhouse", 9000)
    url = "clickhouse://{}:{}/default".format(docker_ip, port)
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1, check=lambda: is_clickhouse_running(url)
    )
    with ClickhouseClient.from_url(url) as click:
        queries = filter(
            lambda x: x != "",
            map(lambda x: x.strip(), read_file("fixtures/clickhouse.sql").split(";")),
        )
        for q in queries:
            click.execute(q)
    yield url


def make_override_get_settings(**kw):
    def override_get_settings():
        return Settings(**kw)

    return override_get_settings


@pytest.fixture
def alembic_migration(postgresql):
    from alembic import command
    from alembic.config import Config

    db_url = f"postgresql://{postgresql.info.user}:@{postgresql.info.host}:{postgresql.info.port}/{postgresql.info.dbname}"

    migrations_path = (
        Path(__file__).parent.parent / "src" / "oonifindings" / "common" / "alembic"
    ).resolve()

    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(migrations_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")
    yield db_url


@pytest.fixture
def client_with_bad_settings():
    app.dependency_overrides[get_settings] = make_override_get_settings(
        postgresql_url="postgresql://badhost:9000"
    )

    client = TestClient(app)
    yield client


@pytest.fixture
def client(alembic_migration, clickhouse_server):
    app.dependency_overrides[get_settings] = make_override_get_settings(
        postgresql_url=alembic_migration,
        clickhouse_url=clickhouse_server,
        jwt_encryption_key="super_secure",
        prometheus_metrics_password="super_secure",
        account_id_hashing_key="super_secure",
    )

    client = TestClient(app)
    yield client


def create_jwt(payload: dict) -> str:
    return jwt.encode(payload, "super_secure", algorithm="HS256")


def create_session_token(account_id: str, email: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "nbf": now,
        "iat": now,
        "exp": now + 10 * 86400,
        "aud": "user_auth",
        "account_id": account_id,
        "email_address": email,
        "login_time": None,
        "role": role,
    }
    return create_jwt(payload)


@pytest.fixture
def client_with_user_role(client):
    client = TestClient(app)
    jwt_token = create_session_token("0" * 16, "oonitarian@example.com", "user")
    client.headers = {"Authorization": f"Bearer {jwt_token}"}
    yield client


@pytest.fixture
def client_with_admin_role(client):
    client = TestClient(app)
    jwt_token = create_session_token("1" * 16, "admin@example.com", "admin")
    client.headers = {"Authorization": f"Bearer {jwt_token}"}
    yield client


@pytest.fixture
def client_with_hashed_email(client):

    def _hashed_email(email: str, role: str):
        client = TestClient(app)
        account_id = hash_email_address(email, "super_secure")
        jwt_token = create_session_token(account_id, email, role)
        client.headers = {"Authorization": f"Bearer {jwt_token}"}
        return client

    return _hashed_email
