import pathlib
import pytest

import time
import jwt

from fastapi.testclient import TestClient

from ooniprobe.common.config import Settings
from ooniprobe.common.dependencies import get_settings
from ooniprobe.main import app


def make_override_get_settings(**kw):
    def override_get_settings():
        return Settings(**kw)

    return override_get_settings


@pytest.fixture
def alembic_migration(postgresql):
    from alembic import command
    from alembic.config import Config

    db_url = f"postgresql://{postgresql.info.user}:@{postgresql.info.host}:{postgresql.info.port}/{postgresql.info.dbname}"

    migrations_path = (pathlib.Path(__file__).parent.parent / "alembic").resolve()

    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(migrations_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")
    yield db_url


@pytest.fixture
def client_with_bad_settings():
    app.dependency_overrides[get_settings] = make_override_get_settings(
        postgresql_url="postgresql://bad:bad@localhost/bad"
    )

    client = TestClient(app)
    yield client


@pytest.fixture
def client(alembic_migration):
    app.dependency_overrides[get_settings] = make_override_get_settings(
        postgresql_url=alembic_migration,
        jwt_encryption_key="super_secure",
        prometheus_metrics_password="super_secure",
    )

    client = TestClient(app)
    yield client
