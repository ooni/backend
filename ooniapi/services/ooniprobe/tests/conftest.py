from tempfile import tempdir
import pathlib
from pathlib import Path
import pytest
import shutil
import os
from urllib.request import urlopen

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from clickhouse_driver import Client as ClickhouseClient

from ooniprobe.common.config import Settings
from ooniprobe.common.dependencies import get_settings
from ooniprobe.dependencies import get_s3_client
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

@pytest.fixture(scope="session")
def fixture_path():
    """
    Directory for this fixtures used to store temporary data, will be 
    deleted after the tests are finished
    """
    FIXTURE_PATH = Path(os.path.dirname(os.path.realpath(__file__))) / "data"

    yield FIXTURE_PATH

    try:
        shutil.rmtree(FIXTURE_PATH)
    except FileNotFoundError:
        pass

@pytest.fixture()
def geoip_db_dir(fixture_path):
    ooni_tempdir = fixture_path / "geoip"
    return str(ooni_tempdir)


@pytest.fixture
def client(clickhouse_server, test_settings, geoip_db_dir):
    app.dependency_overrides[get_settings] = test_settings
    app.dependency_overrides[get_s3_client] = get_s3_client_mock
    # lifespan won't run so do this here to have the DB
    try_update(geoip_db_dir)
    client = TestClient(app)
    yield client


@pytest.fixture
def test_settings(alembic_migration, docker_ip, docker_services, geoip_db_dir, clickhouse_server, fastpath_server):
    yield make_override_get_settings(
        postgresql_url=alembic_migration,
        jwt_encryption_key=JWT_ENCRYPTION_KEY,
        prometheus_metrics_password="super_secure",
        clickhouse_url=clickhouse_server,
        geoip_db_dir=geoip_db_dir,
        collector_id="1",
        fastpath_url=fastpath_server
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

class S3ClientMock:

    def __init__(self) -> None:
        self.files = []

    def upload_fileobj(self, Fileobj, Bucket: str, Key: str):
        self.files.append(f"{Bucket}/{Key}")

def get_s3_client_mock() -> S3ClientMock:
    return S3ClientMock()

@pytest.fixture(scope="session")
def fastpath_server(docker_ip, docker_services):
    port = docker_services.port_for("fakepath", 80)
    url = f"http://{docker_ip}:{port}"
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1, check=lambda: is_fastpath_running(url)
    )
    yield url

def is_fastpath_running(url: str) -> bool: 
    try: 
        resp = urlopen(url)
        return resp.status == 200
    except:
        return False