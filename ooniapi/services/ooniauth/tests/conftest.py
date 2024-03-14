from unittest.mock import MagicMock
import pytest

import time
import jwt

from fastapi.testclient import TestClient

from ooniauth.common.config import Settings
from ooniauth.common.dependencies import get_settings
from ooniauth.dependencies import get_ses_client, get_clickhouse_client
from ooniauth.main import app


def make_override_get_settings(**kw):
    def override_get_settings():
        return Settings(**kw)

    return override_get_settings


@pytest.fixture
def client_with_bad_settings():
    app.dependency_overrides[get_settings] = make_override_get_settings(
        postgresql_url="postgresql://bad:bad@localhost/bad"
    )

    client = TestClient(app)
    yield client


@pytest.fixture
def mock_ses_client():
    mock = MagicMock()
    app.dependency_overrides[get_ses_client] = lambda: mock
    yield mock


@pytest.fixture
def client(mock_ses_client):
    app.dependency_overrides[get_settings] = make_override_get_settings(
        jwt_encryption_key="super_secure",
        prometheus_metrics_password="super_secure",
    )
    mock_clickhouse = MagicMock()
    mock_clickhouse.execute = MagicMock()

    # rows, coldata = q
    # coldata = [("name", "type")]
    mock_clickhouse.execute.return_value = (
        [("user",)],
        [("role", "String")],
    )
    app.dependency_overrides[get_clickhouse_client] = lambda: mock_clickhouse

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
