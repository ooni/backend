"""
Dedicated coverage for the *exact* wire format of every datetime field
returned by the ooniauth API.

ooniauth's response models are built on `ooniauth.common.routers.BaseModel`,
the same shared base class used by oonimeasurements, oonifindings and
oonirun (see ooniapi/common/src/common/routers.py). A change to that shared
serializer can silently change the wire format of every endpoint that uses
it, and neither `UserLogin.login_token_expiration` nor
`UserSession.login_time` had any format assertion before this module -- only
their presence/value was checked (e.g. `j["is_logged_in"] == True`).

`login_time` is populated from two different code paths depending on how the
session is created:
- via a login token (`POST /v2/ooniauth/user-session` with `login_token`):
  `datetime.now(timezone.utc)` -- timezone-aware.
- via an existing session header (`GET`/`POST /v2/ooniauth/user-session`
  with only an `Authorization` header): `datetime.fromtimestamp(...)` with no
  explicit timezone -- naive. Both are exercised here.
"""

import re

from .test_auth_v2 import perform_login

# "2025-07-01T00:00:00.000000Z"
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


def assert_datetime_format(value):
    assert isinstance(value, str), repr(value)
    assert DATETIME_RE.match(value), (
        f"{value!r} does not match the expected datetime format "
        f"(YYYY-MM-DDTHH:MM:SS.ffffffZ)"
    )


def test_user_login_token_expiration_format(
    client, mock_ses_client, user_email, valid_redirect_to_url
):
    d = dict(email_address=user_email, redirect_to=valid_redirect_to_url)
    r = client.post("/api/v2/ooniauth/user-login", json=d)
    assert r.status_code == 200
    assert_datetime_format(r.json()["login_token_expiration"])


def test_user_session_login_time_format_via_login_token(
    client, mock_ses_client, user_email, valid_redirect_to_url
):
    token = perform_login(client, user_email, mock_ses_client, valid_redirect_to_url)
    r = client.post("/api/v2/ooniauth/user-session", json={"login_token": token})
    assert r.status_code == 200
    j = r.json()
    assert j["is_logged_in"] is True
    assert_datetime_format(j["login_time"])


def test_user_session_login_time_format_via_session_header(
    client, mock_ses_client, user_email, valid_redirect_to_url
):
    token = perform_login(client, user_email, mock_ses_client, valid_redirect_to_url)
    r = client.post("/api/v2/ooniauth/user-session", json={"login_token": token})
    assert r.status_code == 200
    headers = {"Authorization": "Bearer " + r.json()["session_token"]}

    # GET /v2/ooniauth/user-session re-derives login_time from the session
    # token via a different code path (datetime.fromtimestamp, naive) than
    # the initial login above (datetime.now(timezone.utc)); both must
    # serialize to the same wire format.
    r = client.get("/api/v2/ooniauth/user-session", headers=headers)
    assert r.status_code == 200
    j = r.json()
    assert j["is_logged_in"] is True
    assert_datetime_format(j["login_time"])

    r = client.post("/api/v2/ooniauth/user-session", headers=headers)
    assert r.status_code == 200
    j = r.json()
    assert j["is_logged_in"] is True
    assert_datetime_format(j["login_time"])
