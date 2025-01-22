import pathlib
import pytest

import time
import jwt

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ooniprobe.common.config import Settings
from ooniprobe.common.dependencies import get_settings
from ooniprobe.main import app


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


@pytest.fixture
def client(alembic_migration):
    app.dependency_overrides[get_settings] = make_override_get_settings(
        postgresql_url=alembic_migration,
        jwt_encryption_key=JWT_ENCRYPTION_KEY,
        prometheus_metrics_password="super_secure",
    )

    client = TestClient(app)
    yield client


@pytest.fixture
def jwt_encryption_key():
    return JWT_ENCRYPTION_KEY
