from tempfile import tempdir
from pathlib import Path
import jwt
import pytest
import shutil
import os
import time
from urllib.request import urlopen

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from clickhouse_driver import Client as ClickhouseClient

from citizenlab.common.config import Settings
from citizenlab.common.dependencies import get_settings
from citizenlab.dependencies import get_s3_client
from citizenlab.main import app


@pytest.fixture()
def citizenlab_tblready(client, app):
    # Ensure the citizenlab table is populated
    r = app.click.execute("SELECT count() FROM citizenlab")[0][0]
    assert r > 2


@pytest.fixture
def url_prio_tblready(app):
    log = app.logger
    # Ensure the url_priorities table is populated
    r = app.click.execute("SELECT count() FROM url_priorities")[0][0]
    if r > 5:
        return

    rules = [
        ("NEWS", 100),
        ("POLR", 100),
        ("HUMR", 100),
        ("LGBT", 100),
        ("ANON", 100),
        ("MMED", 80),
        ("SRCH", 80),
        ("PUBH", 80),
        ("REL", 60),
        ("XED", 60),
        ("HOST", 60),
        ("ENV", 60),
        ("FILE", 40),
        ("CULTR", 40),
        ("IGO", 40),
        ("GOVT", 40),
        ("DATE", 30),
        ("HATE", 30),
        ("MILX", 30),
        ("PROV", 30),
        ("PORN", 30),
        ("GMB", 30),
        ("ALDR", 30),
        ("GAME", 20),
        ("MISC", 20),
        ("HACK", 20),
        ("ECON", 20),
        ("COMM", 20),
        ("CTRL", 20),
        ("COMT", 100),
        ("GRP", 100),
    ]
    rows = [
        {
            "sign": 1,
            "category_code": ccode,
            "cc": "*",
            "domain": "*",
            "url": "*",
            "priority": prio,
        }
        for ccode, prio in rules
    ]
    # The url_priorities table is CollapsingMergeTree
    query = """INSERT INTO url_priorities
        (sign, category_code, cc, domain, url, priority) VALUES
    """
    log.info("Populating url_priorities")
    app.click.execute(query, rows)
    app.click.execute("OPTIMIZE TABLE url_priorities FINAL")


def make_override_get_settings(**kw):
    def override_get_settings():
        return Settings(**kw)

    return override_get_settings


def pytest_addoption(parser):
    parser.addoption("--ghpr", action="store_true", help="enable GitHub integ tests")
    parser.addoption("--proddb", action="store_true", help="uses data from prod DB")
    parser.addoption("--create-db", action="store_true", help="populate the DB")
    parser.addoption(
        "--inject-msmts", action="store_true", help="populate the DB with fresh data"
    )


def pytest_configure(config):
    pytest.run_ghpr = config.getoption("--ghpr")
    pytest.proddb = config.getoption("--proddb")
    assert pytest.proddb is False, "--proddb is disabled"
    pytest.create_db = config.getoption("--create-db")
    pytest.inject_msmts = config.getoption("--inject-msmts")


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
        Path(__file__).parent.parent
        / "src"
        / "citizenlab"
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


@pytest.fixture
def client(clickhouse_server, test_settings):
    app.dependency_overrides[get_settings] = test_settings
    app.dependency_overrides[get_s3_client] = get_s3_client_mock
    # lifespan won't run so do this here to have the DB
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
def test_settings(alembic_migration, clickhouse_server, fastpath_server):
    yield make_override_get_settings(
        postgresql_url=alembic_migration,
        jwt_encryption_key=JWT_ENCRYPTION_KEY,
        prometheus_metrics_password="super_secure",
        clickhouse_url=clickhouse_server,
        collector_id="1",
        fastpath_url=fastpath_server
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
def clickhouse_server(docker_ip, docker_services):
    # replace with pytest-container, but not sure how we get the ip/port
    port = docker_services.port_for("clickhouse", 9000)
    # See password in docker compose
    url = "clickhouse://test:test@{}:{}".format(docker_ip, port)
    docker_services.wait_until_responsive(
        timeout=30.0, pause=1.0, check=lambda: is_clickhouse_running(url)
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
    # replace with pytest-container, but not sure how we get the ip/port
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
