import json
import pathlib
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from urllib.request import urlopen

import ooniauth_py
import pytest
import requests
import ujson
from clickhouse_driver import Client as ClickhouseClient
from fastapi.testclient import TestClient
from pytest_docker.plugin import Services
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ooniprobe.common.clickhouse_utils import insert_click
from ooniprobe.common.config import Settings
from ooniprobe.common.dependencies import get_settings
from ooniprobe.dependencies import (
    Manifest,
    ManifestMeta,
    ManifestResponse,
    _get_manifest,
    get_s3_client,
    get_tor_targets_from_s3,
    get_psiphon_config_from_s3,
)
from ooniprobe.download_geoip import try_update
from ooniprobe.main import app, lifespan
from ooniprobe.routers.v1.probe_services import TorTarget

from .utils import setup_user


def make_override_get_settings(**kw):
    def override_get_settings():
        return Settings(**kw)

    return override_get_settings


@pytest.fixture
def pg_url(postgresql):
    return f"postgresql://{postgresql.info.user}:@{postgresql.info.host}:{postgresql.info.port}/{postgresql.info.dbname}"


@pytest.fixture
def db(pg_url: str):
    engine = create_engine(pg_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def alembic_migration(pg_url: str):
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
def fixture_path(tmp_path_factory):
    """
    Directory for this fixtures used to store temporary data, will be
    deleted after the tests are finished
    """
    yield tmp_path_factory.mktemp("fixtures")


@pytest.fixture()
def geoip_db_dir(fixture_path):
    ooni_tempdir = fixture_path / "geoip"
    return str(ooni_tempdir)


def make_manifest_mock_fn(public_params: str):
    def get_manifest_mock():
        return ManifestResponse(
            manifest=Manifest(
                submission_policy=[
                    {
                        "match": {"probe_cc": "*", "probe_asn": "*"},
                        "policy": {
                            "age": [2461110, 2826140],
                            "measurement_count": 0,
                        },
                    }
                ],
                public_parameters=public_params,
            ),
            meta=ManifestMeta(
                version="1",
                last_modification_date=datetime.now(),
                manifest_url="https://ooni.mock/manifest",
                library_version=ooniauth_py.__version__,
                protocol_version=ooniauth_py.get_protocol_version(),
            ),
        )

    return get_manifest_mock


@pytest_asyncio.fixture
async def client(clickhouse_server, test_settings, geoip_db_dir, test_creds):
    _, public_key = test_creds
    app.dependency_overrides[get_settings] = test_settings
    app.dependency_overrides[get_s3_client] = get_s3_client_mock
    app.dependency_overrides[get_tor_targets_from_s3] = get_tor_targets_from_s3_mock
    app.dependency_overrides[get_psiphon_config_from_s3] = get_psiphon_config_from_s3_mock
    app.dependency_overrides[_get_manifest] = make_manifest_mock_fn(public_key)
    # lifespan won't run so do this here to have the DB
    try_update(geoip_db_dir)
    settings = test_settings()
    async with lifespan(app, settings, repeating_tasks_active=False):
        with TestClient(app) as client:
            yield client


@pytest.fixture
def test_creds():
    """
    Example credentials used for anonymous credentials
    """

    # (Secret key, public key)
    return (
        "AUGQSPO28+QLlf8fKhQjqAD2Ehjn0Q471Yavs7n0qsYJ0nnZ1G/Y2LqvjC3Stq0o9Ka6lB2Xq9EDIEOFhQsjbQQDAAAAAAAAAGk422WHZ5MEPCTMbaj4sDvW27Yvl+pRzDuuTasyEpIDRCEzgL3tIOErnbYtca/68gHUxIfXRCDtcSMEvxVhSAynRFLeT0pXf5fRFwX4gbzNVgvzh0MthADyh7UUPmj6BQ==",
        "AaJpxHsB+x4axWCrFxohF+ML5inYWbPbVQro9YGxb9NVAcgzlHrnd7PLfwWQe69W3ZLcGe4R/CnbFBwhCfdfvvpCAwAAAAAAAAAkAklNBr7fMUrdkeNT360ZsLTGN8A7kKMX6b60tJ5YCBLJ9QJdwnkp12VHPgND2/chraDFw8snqfq0JDZI2tJ04sqKzWi+y57qzh0HG+pkZ3xe7RceyE4isTs7ZRzriwA=",
    )


@pytest.fixture
def test_settings(
    alembic_migration: Any,
    geoip_db_dir: str,
    clickhouse_server: str,
    fastpath_server: str,
    test_creds,
):
    (secret_key, _) = test_creds
    yield make_override_get_settings(
        postgresql_url=alembic_migration,
        jwt_encryption_key=JWT_ENCRYPTION_KEY,
        prometheus_metrics_password="super_secure",
        clickhouse_url=clickhouse_server,
        geoip_db_dir=geoip_db_dir,
        collector_id="1",
        fastpath_urls=[fastpath_server],
        anonc_manifest_bucket="test-bucket",
        anonc_manifest_file="manifest.json",
        anonc_secret_key=secret_key,
        tor_targets="./tests/fixtures/data/tor-targets.json",
        psiphon_config="./tests/fixtures/data/psiphon-config.json"
    )


@pytest.fixture
def jwt_encryption_key():
    return JWT_ENCRYPTION_KEY


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
def clickhouse_server(docker_ip: str | Any, docker_services: Services):
    port = docker_services.port_for("clickhouse", 9000)
    # See password in docker compose
    url = "clickhouse://test:test@{}:{}".format(docker_ip, port)
    docker_services.wait_until_responsive(
        timeout=30.0, pause=1.0, check=lambda: is_clickhouse_running(url)
    )
    yield url


@pytest.fixture(scope="session")
def clickhouse_db(clickhouse_server: str):
    yield ClickhouseClient.from_url(clickhouse_server)


@pytest.fixture(scope="function")
def clean_faulty_measurements(clickhouse_db: ClickhouseClient):
    """
    Ensure faulty_measurements is empty after each test
    """
    yield
    clickhouse_db.execute("TRUNCATE TABLE faulty_measurements")


class S3ClientMock:
    def __init__(self) -> None:
        self.files = []

    def upload_fileobj(self, Fileobj, Bucket: str, Key: str):
        self.files.append(f"{Bucket}/{Key}")


def get_s3_client_mock() -> S3ClientMock:
    return S3ClientMock()


def get_tor_targets_from_s3_mock() -> Dict[str, TorTarget]:
    with open("./tests/fixtures/data/tor-targets.json", "r") as f:
        yield ujson.load(f)

def get_psiphon_config_from_s3_mock() -> Dict[str, TorTarget]:
    with open("./tests/fixtures/data/psiphon-config.json", "r") as f:
        yield ujson.load(f)

@pytest.fixture(scope="session")
def fastpath_server(docker_ip: str | Any, docker_services: Services):
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
    except Exception:
        return False


@pytest.fixture
def load_url_priorities(clickhouse_db: ClickhouseClient):
    path = Path("tests/fixtures/data")
    filename = "url_priorities_us.json"
    file = Path(path, filename)

    with file.open("r") as f:
        j = json.load(f)

    # 'sign' is created with default value 0, causing a db error.
    # use 1 to prevent it
    for row in j:
        row["sign"] = 1

    query = "INSERT INTO url_priorities (sign, category_code, cc, domain, url, priority) VALUES"
    insert_click(clickhouse_db, query, j)


@pytest.fixture(scope="function")
def client_with_original_manifest(client):
    return setup_user(client)


class MockFastpathResponse:
    """
    Mocked fastpath response to emulate fastpath client responses
    """

    def __init__(self, status_code: int):
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class MockFastpathClient:
    """
    This mocked fastpath client that responds with error for some paths, and success with other
    paths.

    Used for testing fastpath responses
    """

    def __init__(self, success_url_prefix: str = "/good/"):
        self.success_url_prefix = success_url_prefix
        self.uploads: dict[str, bytes] = {}

    def post(self, url: str, data: bytes = b"", **kwargs):
        if self.success_url_prefix in url:
            self.uploads[url] = data
            return MockFastpathResponse(200)
        return MockFastpathResponse(502)

    def close(self):
        # called by the app lifespan on shutdown
        pass


@pytest_asyncio.fixture
async def client_with_mocked_fastpath(
    clickhouse_server, test_settings, geoip_db_dir, test_creds
):
    """
    Client variant to test fastpath behaviour, see the mocked fastpath client
    above.

    Yields `(client, mock_fastpath, success_url)`.
    """
    fail_url = "http://fastpath.ooni/bad"
    success_url = "http://fastpath.ooni/good"

    _, public_key = test_creds

    settings = test_settings().model_copy(
        update={
            "fastpath_urls": [fail_url, success_url],
        }
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_s3_client] = get_s3_client_mock
    app.dependency_overrides[get_tor_targets_from_s3] = get_tor_targets_from_s3_mock
    app.dependency_overrides[get_psiphon_config_from_s3] = get_psiphon_config_from_s3_mock
    app.dependency_overrides[_get_manifest] = make_manifest_mock_fn(public_key)
    try_update(geoip_db_dir)

    mock_fastpath = MockFastpathClient()
    async with lifespan(app, settings, repeating_tasks_active=False):
        with TestClient(app) as client:
            app.state.fastpath_client = mock_fastpath
            yield client, mock_fastpath, success_url


@pytest_asyncio.fixture
async def client_with_two_working_fastpaths(
    clickhouse_server, test_settings, geoip_db_dir, test_creds
):
    """
    Client variant to test successful fastpath submissions with two healthy fastpath instances

    Yields `(client, mock_fastpath, first_url, second_url)`.
    """
    first_url = "http://fastpath-a.ooni/good"
    second_url = "http://fastpath-b.ooni/good"

    _, public_key = test_creds

    settings = test_settings().model_copy(
        update={
            "fastpath_urls": [first_url, second_url],
        }
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_s3_client] = get_s3_client_mock
    app.dependency_overrides[get_tor_targets_from_s3] = get_tor_targets_from_s3_mock
    app.dependency_overrides[get_psiphon_config_from_s3] = get_psiphon_config_from_s3_mock
    app.dependency_overrides[_get_manifest] = make_manifest_mock_fn(public_key)
    try_update(geoip_db_dir)

    mock_fastpath = MockFastpathClient()
    async with lifespan(app, settings, repeating_tasks_active=False):
        with TestClient(app) as client:
            app.state.fastpath_client = mock_fastpath
            yield client, mock_fastpath, first_url, second_url
