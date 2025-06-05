import pathlib
from pathlib import Path
import pytest
import json
import random
from datetime import datetime, timedelta, UTC

import time
import jwt

from fastapi.testclient import TestClient

from oonirun.common.config import Settings
from oonirun.common.clickhouse_utils import insert_click
from oonirun.common.dependencies import get_settings
from oonirun.main import app
from clickhouse_driver import Client as ClickhouseClient

THIS_DIR = Path(__file__).parent.resolve()


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
        pathlib.Path(__file__).parent.parent / "src" / "oonirun" / "common" / "alembic"
    ).resolve()

    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(migrations_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")
    yield db_url


@pytest.fixture
def client_with_bad_settings():
    app.dependency_overrides[get_settings] = make_override_get_settings(
        postgresql_url="postgresql://bad:bad@localhost/bad",
        clickhouse_url="clickhouse://bad:bad@localhost/bad",
    )

    client = TestClient(app)
    yield client


@pytest.fixture
def client(alembic_migration, clickhouse_server):
    app.dependency_overrides[get_settings] = make_override_get_settings(
        postgresql_url=alembic_migration,
        jwt_encryption_key="super_secure",
        prometheus_metrics_password="super_secure",
        clickhouse_url=clickhouse_server,
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
        "email_address": "oonitarian@example.com",
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
    # See password in docker compose
    url = "clickhouse://test:test@{}:{}".format(docker_ip, port)
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1, check=lambda: is_clickhouse_running(url)
    )
    yield url


@pytest.fixture(scope="session")
def clickhouse_db(clickhouse_server):
    yield ClickhouseClient.from_url(clickhouse_server)


@pytest.fixture(scope="module")
def fixtures_data_dir():
    yield Path(THIS_DIR, "fixtures/data")


@pytest.fixture(scope="module")
def url_priorities(clickhouse_db, fixtures_data_dir):
    filename = "url_priorities_us.json"
    file = Path(fixtures_data_dir, filename)

    with file.open("r") as f:
        j = json.load(f)

    # 'sign' is created with default value 0, causing a db error.
    # use 1 to prevent it
    for row in j:
        row["sign"] = 1

    query = "INSERT INTO url_priorities (sign, category_code, cc, domain, url, priority) VALUES"
    insert_click(clickhouse_db, query, j)
    yield
    clickhouse_db.execute("TRUNCATE TABLE url_priorities")


def generate_random_date_last_7_days() -> datetime:
    start = datetime.now(tz=UTC) - timedelta(days=7)

    # return a random date between 7 days ago and now
    return start + timedelta(
        seconds=random.randrange(3600 * 24, 3600 * 24 * 7 - 3600 * 24)
    )


@pytest.fixture(scope="module")
def measurements(clickhouse_db, fixtures_data_dir):
    msmnts_dir = Path(fixtures_data_dir, "measurements.json")
    with open(msmnts_dir, "r") as f:
        measurements = json.load(f)

    for ms in measurements:
        date = generate_random_date_last_7_days()
        ms["measurement_start_time"] = date
        ms["test_start_time"] = date

    query = "INSERT INTO fastpath VALUES"
    insert_click(clickhouse_db, query, measurements)

    yield
    clickhouse_db.execute("TRUNCATE TABLE url_priorities")


@pytest.fixture
def super_prioritized_website(clickhouse_db):
    values = {
        "category_code": "*",
        "cc": "*",
        "domain": "ooni.org",
        "priority": 99999,
        "url": "*",
        "sign": 1,
    }
    query = "INSERT INTO url_priorities (sign, category_code, cc, domain, url, priority) VALUES"
    insert_click(clickhouse_db, query, [values])
    yield
    clickhouse_db.execute("DELETE FROM url_priorities WHERE domain='ooni.org'")
