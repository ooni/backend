"""
Integration test for Auth API

Warning: this test runs against a real database and SMTP

Lint using:
    black -t py37 -l 100 --fast ooniapi/tests/integ/test_probe_services.py

Test using:
    pytest-3 -s --show-capture=no ooniapi/tests/integ/test_integration_auth.py
"""

from unittest.mock import MagicMock, Mock
from urllib.parse import urlparse

import pytest
from freezegun import freeze_time  # debdeps: python3-freezegun

import ooniapi.auth


@pytest.fixture()
def log(app):
    return app.logger


@pytest.fixture(autouse=True, scope="session")
def setup_test_session():
    # mock smtplib
    m = Mock(name="MockSMTPInstance")
    s = Mock(name="SMTP session")
    x = Mock(name="mock enter", return_value=s)
    m.__enter__ = x
    m.__exit__ = Mock(name="mock exit")
    setup_test_session.mocked_s = s
    ooniapi.auth.smtplib.SMTP = Mock(name="MockSMTP", return_value=m)
    ooniapi.auth.smtplib.SMTP_SSL = MagicMock()


admin_e = "integtest@openobservatory.org"
user_e = "nick@localhost.local"


@pytest.fixture
def integtest_admin(app):
    # Access DB directly
    with app.app_context():
        ooniapi.auth._set_account_role(admin_e, "admin")
        yield
        ooniapi.auth._delete_account_data(admin_e)


@pytest.fixture
def adminsession(client, app):
    # Access DB directly
    # Mock out SMTP, register a user and log in
    with app.app_context():
        ooniapi.auth._set_account_role(admin_e, "admin")
        _register_and_login(client, admin_e)
        reset_smtp_mock()
        yield
        ooniapi.auth._delete_account_data(admin_e)
        reset_smtp_mock()


def reset_smtp_mock():
    ooniapi.auth.smtplib.SMTP.reset_mock()
    ooniapi.auth.smtplib.SMTP_SSL.reset_mock()


@pytest.fixture()
def mocksmtp():
    reset_smtp_mock()


def postj(client, url, **kw):
    response = client.post(url, json=kw)
    assert response.status_code == 200
    return response


# # Tests


def test_login_user_bogus_token(client, mocksmtp):
    r = client.get("/api/v1/user_login?k=BOGUS")
    assert r.status_code == 401
    assert r.json == {"error": "Invalid credentials"}


def test_user_register_non_valid(client, mocksmtp):
    d = dict(nickname="", email_address=user_e)
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 400
    assert r.json == {"error": "Invalid user name"}

    d = dict(nickname="x", email_address=user_e)
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 400
    assert r.json == {"error": "User name is too short"}

    d = dict(nickname="nick", email_address="nick@localhost")
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 400
    assert r.json == {"error": "Invalid email address"}


def _register_and_login(client, email_address):
    # # return cookie header for further use
    d = dict(nickname="nick", email_address=email_address)
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 200
    assert r.json == {"msg": "ok"}

    ooniapi.auth.smtplib.SMTP.assert_called_once()
    ooniapi.auth.smtplib.SMTP_SSL.assert_not_called()
    setup_test_session.mocked_s.send_message.assert_called_once()
    msg = setup_test_session.mocked_s.send_message.call_args[0][0]
    msg = str(msg)
    url = None
    assert "Subject: OONI Account activation" in msg
    assert msg
    for line in msg.splitlines():
        if '<a href="https://' in line:
            url = line.split('"')[1]
    assert url
    u = urlparse(url)
    token = u.query.split('=')[1]
    assert len(token) > 0

    r = client.get(f"/api/v1/user_login?k={token}")
    assert r.status_code == 200
    cookies = r.headers.getlist("Set-Cookie")
    assert len(cookies) == 1
    c = cookies[0]
    assert c.startswith("ooni=")
    assert c.endswith("; Secure; HttpOnly; Path=/")
    return {"Set-Cookie": c}


def test_user_register_and_get_metadata(client, mocksmtp):
    r = client.get("/api/_/account_metadata")
    assert r.json == {}
    _register_and_login(client, user_e)
    r = client.get("/api/_/account_metadata")
    assert r.json == {"nick": "nick", "role": "user"}


def test_role_set_not_allowed(client, mocksmtp):
    # We are not logged in and not allowed to call this
    d = dict(email_address=admin_e, role="admin")
    r = client.post("/api/v1/set_account_role", json=d)
    assert r.status_code == 401

    _register_and_login(client, user_e)

    # We are logged in with role "user" and still not allowed to call this
    d = dict(email_address=admin_e, role="admin")
    r = client.post("/api/v1/set_account_role", json=d)
    assert r.status_code == 401

    r = client.get("/api/v1/get_account_role/integtest@openobservatory.org")
    assert r.status_code == 401


def test_role_set(client, mocksmtp, integtest_admin):
    _register_and_login(client, admin_e)

    # We are logged in with role "admin"
    d = dict(email_address=admin_e, role="admin")
    r = client.post("/api/v1/set_account_role", json=d)
    assert r.status_code == 200

    d = dict(email_address="BOGUS_EMAIL_ADDR", role="admin")
    r = client.post("/api/v1/set_account_role", json=d)
    assert r.status_code == 400

    d = dict(email_address=admin_e, role="BOGUS_ROLE")
    r = client.post("/api/v1/set_account_role", json=d)
    assert r.status_code == 400

    r = client.get("/api/v1/get_account_role/integtest@openobservatory.org")
    assert r.status_code == 200
    assert r.json == {"role": "admin"}

    r = client.get("/api/v1/get_account_role/BOGUS_EMAIL_ADDR")
    assert r.status_code == 400

    r = client.get("/api/v1/get_account_role/valid_but_not_found@example.org")
    assert r.status_code == 400
    assert r.json == {"error": "Account not found"}

    d = dict(email_address=admin_e, role="user")
    r = client.post("/api/v1/set_account_role", json=d)
    assert r.status_code == 200


def test_role_set_with_expunged_token(client, mocksmtp, integtest_admin):
    _register_and_login(client, admin_e)

    d = dict(email_address="BOGUS_EMAIL_ADDR", role="admin")
    r = client.post("/api/v1/set_session_expunge", json=d)
    assert r.status_code == 400

    # As admin, I expunge my own session token
    d = dict(email_address=admin_e, role="admin")
    r = client.post("/api/v1/set_session_expunge", json=d)
    assert r.status_code == 200

    r = client.get("/api/v1/get_account_role/" + admin_e)
    assert r.status_code == 401


def decode_token(client):
    # Decode JWT token in the cookie jar
    assert len(client.cookie_jar) == 1
    cookie = list(client.cookie_jar)[0].value
    tok = ooniapi.auth.decode_jwt(cookie, audience="user_auth")
    return tok


def test_session_refresh_and_expire(client, mocksmtp, integtest_admin):
    # Using:
    # SESSION_EXPIRY_DAYS = 2
    # LOGIN_EXPIRY_DAYS = 7
    with freeze_time("2012-01-14"):
        ooniapi.auth._remove_from_session_expunge(admin_e)
        _register_and_login(client, admin_e)
        tok = decode_token(client)
        assert tok == {
            "nbf": 1326499200,
            "iat": 1326499200,
            "exp": 1326672000,
            "aud": "user_auth",
            "account_id": "71e398652ecfb1be6a2359923c7df008",
            "login_time": 1326499200,
            "nick": "nick",
            "role": "admin",
        }
        r = client.get("/api/v1/get_account_role/integtest@openobservatory.org")
        assert r.status_code == 200

    with freeze_time("2012-01-15"):
        # The session is still valid but the token will be replaced
        r = client.get("/api/v1/get_account_role/integtest@openobservatory.org")
        assert r.status_code == 200
        assert r.json == {"role": "admin"}
        assert decode_token(client) == {
            "nbf": 1326585600,
            "iat": 1326585600,
            "exp": 1326758400,
            "aud": "user_auth",
            "account_id": "71e398652ecfb1be6a2359923c7df008",
            "login_time": 1326499200,
            "nick": "nick",
            "role": "admin",
        }

    with freeze_time("2012-02-01"):
        # The login is expired
        r = client.get("/api/v1/get_account_role/integtest@openobservatory.org")
        assert r.status_code == 401
