from tempfile import tempdir
import pathlib
from pathlib import Path
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from clickhouse_driver import Client as ClickhouseClient
import requests

from ooniprobe.common.config import Settings
from ooniprobe.common.dependencies import get_settings
from ooniprobe.main import app
from ooniprobe.download_geoip import try_update


def make_override_get_settings(**kw):
    def override_get_settings():
        return Settings(**kw)

    return override_get_settings


@pytest.fixture
def pg_url(postgresql):
    return f"postgresql://{postgresql.info.user}:@{postgresql.info.host}:{postgresql.info.port}/{postgresql.info.dbname}"


@pytest.fixture
def db(pg_url):
    engine = create_engine(pg_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def alembic_migration(pg_url):
    from alembic import command
    from alembic.config import Config

    migrations_path = (
        pathlib.Path(__file__).parent.parent
        / "src"
        / "ooniprobe"
        / "common"
        / "alembic"
    ).resolve()

    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(migrations_path))
    alembic_cfg.set_main_option("sqlalchemy.url", pg_url)

    command.upgrade(alembic_cfg, "head")
    yield pg_url


@pytest.fixture
def client_with_bad_settings():
    app.dependency_overrides[get_settings] = make_override_get_settings(
        postgresql_url="postgresql://bad:bad@localhost/bad"
    )

    client = TestClient(app)
    yield client


JWT_ENCRYPTION_KEY = "super_secure"
GEOIP_DB_DIR = f"{tempdir}/ooni/geoip"


@pytest.fixture
def client(alembic_migration, clickhouse_server, test_settings):
    app.dependency_overrides[get_settings] = test_settings
    # lifespan won't run so do this here to have the DB 
    try_update(GEOIP_DB_DIR)
    client = TestClient(app)
    yield client

@pytest.fixture
def test_settings(alembic_migration, docker_ip, docker_services):
    port = docker_services.port_for("clickhouse", 9000)
    yield make_override_get_settings(
        postgresql_url=alembic_migration,
        jwt_encryption_key=JWT_ENCRYPTION_KEY,
        prometheus_metrics_password="super_secure",
        clickhouse_url=f"clickhouse://test:test@{docker_ip}:{port}",
        geoip_db_dir = GEOIP_DB_DIR
    )

@pytest.fixture
def jwt_encryption_key():
    return JWT_ENCRYPTION_KEY

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