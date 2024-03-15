from unittest.mock import MagicMock
import pytest

import time
import jwt

from fastapi.testclient import TestClient

from ooniauth.common.config import Settings
from ooniauth.common.dependencies import get_settings
from ooniauth.dependencies import get_ses_client, get_clickhouse_client
from ooniauth.utils import hash_email_address
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
def user_email():
    return "dev+useraccount@ooni.org"


@pytest.fixture
def admin_email():
    return "dev+adminaccount@ooni.org"


@pytest.fixture
def jwt_encryption_key():
    return "super_secure"


@pytest.fixture
def prometheus_password():
    return "super_secure"


@pytest.fixture
def account_id_hashing_key():
    return "super_secure"


@pytest.fixture
def email_source_address():
    return "admin+sourceemail@ooni.org"


@pytest.fixture
def valid_redirect_to_url():
    return "https://explorer.ooni.org"


@pytest.fixture
def mock_ses_client():
    mock = MagicMock()
    app.dependency_overrides[get_ses_client] = lambda: mock
    yield mock


@pytest.fixture
def mock_misconfigured_ses_client():
    mock = MagicMock()
    mock.send_email.side_effect = Exception("failing to send an email")
    app.dependency_overrides[get_ses_client] = lambda: mock
    yield mock


@pytest.fixture
def client(
    mock_ses_client,
    admin_email,
    jwt_encryption_key,
    account_id_hashing_key,
    prometheus_password,
    email_source_address,
):
    app.dependency_overrides[get_settings] = make_override_get_settings(
        jwt_encryption_key=jwt_encryption_key,
        prometheus_metrics_password=prometheus_password,
        email_source_address=email_source_address,
        account_id_hashing_key=account_id_hashing_key,
        aws_access_key_id="ITSCHANGED",
        aws_secret_access_key="ITSCHANGED",
    )
    mock_clickhouse = MagicMock()
    mock_clickhouse.execute = MagicMock()

    # rows, coldata = q
    # coldata = [("name", "type")]
    def mock_execute(query, query_params, with_column_types, settings):
        assert with_column_types == True
        print(settings)
        assert query.startswith("SELECT role FROM")
        if query_params["account_id"] == hash_email_address(
            email_address=admin_email, key=account_id_hashing_key
        ):
            return [("admin",)], [("role", "String")]

        return [("user",)], [("role", "String")]

    mock_clickhouse.execute = mock_execute
    app.dependency_overrides[get_clickhouse_client] = lambda: mock_clickhouse

    client = TestClient(app)
    yield client
