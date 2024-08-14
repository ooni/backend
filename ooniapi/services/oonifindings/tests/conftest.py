from pathlib import Path
import pytest

import time
import jwt

from fastapi.testclient import TestClient

from oonifindings.common.config import Settings
from oonifindings.common.auth import hash_email_address
from oonifindings.common.dependencies import get_settings
from oonifindings.main import app

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
def client(alembic_migration):
    app.dependency_overrides[get_settings] = make_override_get_settings(
        postgresql_url=alembic_migration,
        jwt_encryption_key="super_secure",
        prometheus_metrics_password="super_secure",
        account_id_hashing_key="super_secure"
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
