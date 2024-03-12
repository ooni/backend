import pytest

import time
import jwt
from pathlib import Path

from fastapi.testclient import TestClient

from oonirun.common.config import Settings
from oonirun.common.dependencies import get_settings
from oonirun.main import app


def setup_db_with_alembic(db_url):
    from alembic import command
    from alembic.config import Config

    migrations_path = (
        Path(__file__).parent.parent / "src" / "oonirun" / "alembic"
    ).resolve()

    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(migrations_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")


def make_override_get_settings(**kw):
    def override_get_settings():
        return Settings(**kw)

    return override_get_settings


@pytest.fixture
def client(postgresql):
    db_url = f"postgresql://{postgresql.info.user}:@{postgresql.info.host}:{postgresql.info.port}/{postgresql.info.dbname}"
    setup_db_with_alembic(db_url)

    app.dependency_overrides[get_settings] = make_override_get_settings(
        postgresql_url=db_url
    )

    client = TestClient(app)
    yield client


def create_jwt(payload: dict) -> str:
    settings = Settings()
    key = settings.jwt_encryption_key
    token = jwt.encode(payload, key, algorithm="HS256")
    if isinstance(token, bytes):
        return token.decode()
    else:
        return token


def create_session_token(account_id: str, role: str, login_time=None) -> str:
    now = int(time.time())
    if login_time is None:
        login_time = now
    payload = {
        "nbf": now,
        "iat": now,
        "exp": now + 10 * 86400,
        "aud": "user_auth",
        "account_id": account_id,
        "login_time": login_time,
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
