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
import quopri

import pytest
from freezegun import freeze_time  # debdeps: python3-freezegun

import ooniapi.auth
import ooniapi.database


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


class AuthClient:
    # wrap Flask http client to provide Authorization=Bearer header
    def __init__(self, http_client, headers):
        self._headers = headers
        self._client = http_client

    def get(self, *a, **kw):
        return self._client.get(*a, **kw, headers=self._headers)

    def post(self, *a, **kw):
        return self._client.post(*a, **kw, headers=self._headers)

    def discard_authorization_header(self):
        self._headers.pop("Authorization")


# setup_test_session mocks SMTP when the test session starts


@pytest.fixture
def usersession(client, app):
    # Mock out SMTP, register a user and log in
    user_e = "nick@localhost.local"
    reset_smtp_mock()
    with app.app_context():
        headers = _register_and_login(client, user_e)
    reset_smtp_mock()
    yield AuthClient(client, headers)
    reset_smtp_mock()


@pytest.fixture
def adminsession(client, app):
    # Access DB directly
    # Mock out SMTP, register a user and log in
    with app.app_context():
        ooniapi.auth._set_account_role(admin_e, "admin")
        headers= _register_and_login(client, admin_e)
        reset_smtp_mock()
        yield AuthClient(client, headers)
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


def test_user_register_non_valid_email(client, mocksmtp):
    d = dict(
        email_address="nick@localhost", redirect_to="https://explorer.ooni.org"
    )  # no FQDN
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 400
    assert r.json == {"error": "Invalid email address"}


def test_user_register_non_valid_redirect(client, mocksmtp):
    d = dict(
        email_address="nick@a.org", redirect_to="https://BOGUS.ooni.org"
    )  # bogus fqdn
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 400
    assert r.json == {"error": "Invalid request"}


def _register_and_login(client, email_address):
    ooniapi.auth._remove_from_session_expunge(email_address)
    # # return cookie header for further use
    d = dict(email_address=email_address, redirect_to="https://explorer.ooni.org")
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
    # Decode MIME-quoted email
    msg = quopri.decodestring(msg)
    # Look for login URL in HTML
    for line in msg.splitlines():
        if b'<a href="https://explorer.ooni.org/login?token=' in line:
            assert b"Please login here" in line
            line = line.decode()
            url = line.split('"')[1]
            break

    assert url, msg
    u = urlparse(url)
    token = u.query.split("=")[1]
    assert len(token) in (323, 335)

    r = client.get(f"/api/v1/user_login?k={token}")
    assert r.status_code == 200, r.json
    assert r.json["redirect_to"] == "https://explorer.ooni.org"
    assert "bearer" in r.json
    return {"Authorization": "Bearer " + r.json["bearer"]}


def test_user_register_and_logout(client, mocksmtp):
    assert client.get("/api/_/account_metadata").json == {
        "logged_in": False
    }  # not logged in
    h = _register_and_login(client, user_e)
    j = client.get("/api/_/account_metadata", headers=h).json
    assert j == {"logged_in": True, "role": "user"}  # logged in
    # simulate logout by not using the token in variable "h"
    j = client.get("/api/_/account_metadata").json
    assert j == {"logged_in": False}


def test_user_register_and_get_metadata(client, mocksmtp):
    r = client.get("/api/_/account_metadata")
    assert r.json == {"logged_in": False}
    h = _register_and_login(client, user_e)
    r = client.get("/api/_/account_metadata", headers=h)
    assert r.json == dict(role="user", logged_in=True)


def test_role_set_not_allowed(client, mocksmtp):
    # We are not logged in and not allowed to call this
    d = dict(email_address=admin_e, role="admin")
    r = client.post("/api/v1/set_account_role", json=d)
    assert r.status_code == 401

    h = _register_and_login(client, user_e)

    # We are logged in with role "user" and still not allowed to call this
    d = dict(email_address=admin_e, role="admin")
    r = client.post("/api/v1/set_account_role", json=d, headers=h)
    assert r.status_code == 401

    r = client.get("/api/v1/get_account_role/integtest@openobservatory.org")
    assert r.status_code == 401


def test_role_set_multiple(client, mocksmtp, integtest_admin):
    h = _register_and_login(client, admin_e)

    # We are logged in with role "admin"
    d = dict(email_address=admin_e, role="admin")
    r = client.post("/api/v1/set_account_role", json=d, headers=h)
    assert r.status_code == 200, r.json

    d = dict(email_address="BOGUS_EMAIL_ADDR", role="admin")
    r = client.post("/api/v1/set_account_role", json=d, headers=h)
    assert r.status_code == 400

    d = dict(email_address=admin_e, role="BOGUS_ROLE")
    r = client.post("/api/v1/set_account_role", json=d, headers=h)
    assert r.status_code == 400

    r = client.get("/api/v1/get_account_role/integtest@openobservatory.org", headers=h)
    assert r.status_code == 200
    assert r.json == {"role": "admin"}

    r = client.get("/api/v1/get_account_role/BOGUS_EMAIL_ADDR", headers=h)
    assert r.status_code == 400

    r = client.get(
        "/api/v1/get_account_role/valid_but_not_found@example.org", headers=h
    )
    assert r.status_code == 400
    assert r.json == {"error": "Account not found"}

    d = dict(email_address=admin_e, role="user")
    r = client.post("/api/v1/set_account_role", json=d, headers=h)
    assert r.status_code == 200


@pytest.mark.skip("FIXME not deterministic, see auth.py  _delete_account_data")
def test_role_set_with_expunged_token(client, mocksmtp, integtest_admin):
    h = _register_and_login(client, admin_e)

    d = dict(email_address="BOGUS_EMAIL_ADDR", role="admin")
    r = client.post("/api/v1/set_session_expunge", json=d)
    assert r.status_code == 400, r.json

    # As admin, I expunge my own session token
    d = dict(email_address=admin_e, role="admin")
    r = client.post("/api/v1/set_session_expunge", json=d)
    assert r.status_code == 200

    r = client.get("/api/v1/get_account_role/" + admin_e)
    assert r.status_code == 401


def decode_token(header):
    # mimics auth.py:get_client_token()
    assert isinstance(header, dict)
    bt = header["Authorization"]
    assert bt.startswith("Bearer ")
    raw_token = bt[7:]
    tok = ooniapi.auth.decode_jwt(raw_token, audience="user_auth")
    return tok


def test_session_refresh_and_expire(client, mocksmtp, integtest_admin):
    # Using:
    # SESSION_EXPIRY_DAYS = 2
    # LOGIN_EXPIRY_DAYS = 7
    with freeze_time("2012-01-14"):
        ooniapi.auth._remove_from_session_expunge(admin_e)
        h = _register_and_login(client, admin_e)
        tok = decode_token(h)
        assert tok == {
            "nbf": 1326499200,
            "iat": 1326499200,
            "exp": 1326672000,
            "aud": "user_auth",
            "account_id": "71e398652ecfb1be6a2359923c7df008",
            "login_time": 1326499200,
            "role": "admin",
        }
        r = client.get(
            "/api/v1/get_account_role/integtest@openobservatory.org", headers=h
        )
        assert r.status_code == 200

    with freeze_time("2012-01-15"):
        r = client.get(
            "/api/v1/get_account_role/integtest@openobservatory.org", headers=h
        )
        assert r.status_code == 200
        assert r.json == {"role": "admin"}
        assert decode_token(h) == {
            "nbf": 1326499200,
            "iat": 1326499200,
            "exp": 1326672000,
            "aud": "user_auth",
            "account_id": "71e398652ecfb1be6a2359923c7df008",
            "login_time": 1326499200,
            "role": "admin",
        }

    with freeze_time("2012-02-01"):
        # The login is expired
        r = client.get(
            "/api/v1/get_account_role/integtest@openobservatory.org", headers=h
        )
        assert r.status_code == 401


# # msmt_feedback


@pytest.fixture(scope="session")
def msmt_tbl(app):
    query_del = """ALTER TABLE msmt_feedback DELETE
        WHERE measurement_uid = 'bogus_uid'"""
    query = "INSERT INTO msmt_feedback (measurement_uid, account_id, status) VALUES"
    rows = [
        ("bogus_uid", "bogus_acc_1", "ok"),
        ("bogus_uid", "bogus_acc_2", "ok"),
        ("bogus_uid", "bogus_acc_3", "blocked"),
    ]
    with app.app_context():
        app.click.execute(query_del)
        ooniapi.database.insert_click(query, rows)


def test_msmt_feedback_get_no_auth(client, msmt_tbl):
    r = client.get("/api/_/measurement_feedback/bogus_uid")
    assert r.json == {"summary": {"blocked": 1, "ok": 2}}


def test_msmt_feedback_submit_no_auth(client, msmt_tbl):
    d = dict(status="foo", measurement_uid="bogus_uid")
    r = client.post("/api/_/measurement_feedback", json=d)
    assert r.json == {"error": "Authentication required"}

    r = client.get("/api/_/measurement_feedback/nonexistent_uid")
    assert r.json == {"summary": {}}


def test_msmt_feedback_submit_valid_and_get(client, mocksmtp, msmt_tbl):
    # We are not logged in and not allowed to call this
    d = dict(status="ok", measurement_uid="bogus_uid")
    r = client.post("/api/_/measurement_feedback", json=d)
    assert r.json == {"error": "Authentication required"}

    # Log in as user
    h = _register_and_login(client, user_e)
    d = dict(status="ok", measurement_uid="bogus_uid")
    r = client.post("/api/_/measurement_feedback", json=d, headers=h)
    assert r.json == {}, r.json

    # Read it back
    r = client.get("/api/_/measurement_feedback/bogus_uid", headers=h)
    assert r.json == {"summary": {"blocked": 1, "ok": 3}, "user_feedback": "ok"}

    # Change feedback
    d = dict(status="blocked", measurement_uid="bogus_uid")
    r = client.post("/api/_/measurement_feedback", json=d, headers=h)
    assert r.json == {}, r.json

    # Read it back again
    r = client.get("/api/_/measurement_feedback/bogus_uid", headers=h)
    assert r.json == {"summary": {"blocked": 2, "ok": 2}, "user_feedback": "blocked"}
