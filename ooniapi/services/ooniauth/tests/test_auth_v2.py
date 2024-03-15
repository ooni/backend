"""
Integration test for Auth API

Warning: this test runs against a real database and SMTP

Lint using:
    black -t py37 -l 100 --fast ooniapi/tests/integ/test_probe_services.py

Test using:
    pytest-3 -s --show-capture=no ooniapi/tests/integ/test_integration_auth.py
"""

from urllib.parse import parse_qs, urlparse
from ooniauth.common.utils import decode_jwt
from ooniauth.main import app
from freezegun import freeze_time


def perform_login(client, email_address, mock_ses_client, valid_redirect_to_url):
    d = dict(email_address=email_address, redirect_to=valid_redirect_to_url)
    r = client.post("/api/v2/ooniauth/user-login", json=d)
    j = r.json()
    assert r.status_code == 200
    assert j["email_address"] == email_address

    from html.parser import HTMLParser

    class AHrefParser(HTMLParser):
        links = []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                for attr in attrs:
                    if attr[0] == "href":
                        self.links.append(attr[1])

    mock_send_email = mock_ses_client.send_email
    assert (
        mock_send_email.call_args.kwargs["Destination"]["ToAddresses"][0]
        == email_address
    )
    html_message = mock_send_email.call_args.kwargs["Message"]["Body"]["Html"]["Data"]
    assert "source" in mock_send_email.call_args.kwargs["Source"]
    parser = AHrefParser()
    parser.feed(html_message)
    parser.close()

    login_link = parser.links[0]
    token = parse_qs(urlparse(login_link).query)["token"][0]
    assert len(token) > 300
    return token


def login_and_make_session(
    client, email_address, mock_ses_client, valid_redirect_to_url
):
    token = perform_login(
        client,
        email_address=email_address,
        mock_ses_client=mock_ses_client,
        valid_redirect_to_url=valid_redirect_to_url,
    )
    r = client.post(f"/api/v2/ooniauth/user-session", json={"login_token": token})
    j = r.json()
    assert r.status_code == 200, j
    assert j["redirect_to"] == valid_redirect_to_url
    assert "session_token" in j
    return {"Authorization": "Bearer " + j["session_token"]}


def test_login_user_bogus_token(client):
    r = client.post(f"/api/v2/ooniauth/user-session", json={"login_token": "INVALID"})
    assert r.status_code == 401
    # Note the key changed from "error" to "detail"
    assert r.json() == {"detail": "Invalid credentials"}


def test_user_register_non_valid_email(client, valid_redirect_to_url):
    d = dict(
        email_address="nick@localhost", redirect_to=valid_redirect_to_url
    )  # no FQDN
    r = client.post("/api/v2/ooniauth/user-login", json=d)
    assert r.status_code == 422
    j = r.json()
    assert j["detail"][0]["loc"] == ["body", "email_address"]


def test_user_register_non_valid_redirect(client, valid_redirect_to_url):
    d = dict(
        email_address="nick@a.org", redirect_to="https://BOGUS.example.com"
    )  # bogus fqdn
    r = client.post("/api/v2/ooniauth/user-login", json=d)
    assert r.status_code == 422

    d = dict(
        email_address="nick@a.org",
        redirect_to=valid_redirect_to_url.replace("https", "http"),
    )  # bogus fqdn
    r = client.post("/api/v2/ooniauth/user-login", json=d)
    assert r.status_code == 422


def test_user_register_missing_redirect(client, valid_redirect_to_url):
    d = dict(email_address="nick@a.org", redirect_to=valid_redirect_to_url)
    r = client.post("/api/v2/ooniauth/user-login", json=d)

    assert r.status_code == 200


def test_user_refresh(client, mock_ses_client, user_email, valid_redirect_to_url):
    r = client.post(
        "/api/v2/ooniauth/user-session",
        headers={"Authorization": "Bearer invalidtoken"},
    )
    assert r.status_code != 200
    j = r.json()

    h = login_and_make_session(
        client, user_email, mock_ses_client, valid_redirect_to_url
    )
    j = client.get("/api/v2/ooniauth/user-session", headers=h).json()
    assert j["is_logged_in"] == True
    assert j["role"] == "user"

    j = client.post("/api/v2/ooniauth/user-session", headers=h).json()
    assert len(j["session_token"]) > 100


def test_user_register_and_refresh(
    client, mock_ses_client, user_email, valid_redirect_to_url
):
    j = client.get("/api/v2/ooniauth/user-session").json()
    assert j["is_logged_in"] == False
    h = login_and_make_session(
        client, user_email, mock_ses_client, valid_redirect_to_url
    )
    j = client.post("/api/v2/ooniauth/user-session", headers=h).json()
    assert j["is_logged_in"] == True
    assert j["role"] == "user"

    # Can't refresh wihtout credentials
    r = client.post("/api/v2/ooniauth/user-session")
    assert r.status_code != 200

    # Can't refresh with empty token
    r = client.post("/api/v2/ooniauth/user-session", json={"login_token": None})
    assert r.status_code != 200


def test_user_register_misconfigured_email(
    client, mock_misconfigured_ses_client, user_email, valid_redirect_to_url
):
    d = dict(email_address=user_email, redirect_to=valid_redirect_to_url)
    r = client.post("/api/v2/ooniauth/user-login", json=d)
    assert r.status_code != 200
    assert isinstance(mock_misconfigured_ses_client.send_email.side_effect, Exception)


def test_user_register_and_get_metadata(
    client, mock_ses_client, user_email, valid_redirect_to_url
):
    j = client.get("/api/v2/ooniauth/user-session").json()
    assert j["is_logged_in"] == False
    h = login_and_make_session(
        client, user_email, mock_ses_client, valid_redirect_to_url
    )
    j = client.get("/api/v2/ooniauth/user-session", headers=h).json()
    assert j["role"] == "user"
    assert j["is_logged_in"] == True


def test_admin_register_and_get_metadata(
    client, mock_ses_client, admin_email, valid_redirect_to_url
):
    j = client.get("/api/v2/ooniauth/user-session").json()
    assert j["is_logged_in"] == False
    h = login_and_make_session(
        client, admin_email, mock_ses_client, valid_redirect_to_url
    )
    j = client.get("/api/v2/ooniauth/user-session", headers=h).json()
    assert j["role"] == "admin"
    assert j["is_logged_in"] == True


def test_user_register_timetravel(
    client, mock_ses_client, user_email, valid_redirect_to_url
):
    with freeze_time("1990-01-01"):
        token = perform_login(
            client,
            email_address=user_email,
            mock_ses_client=mock_ses_client,
            valid_redirect_to_url=valid_redirect_to_url,
        )
        r = client.post(f"/api/v2/ooniauth/user-session", json={"login_token": token})
        j = r.json()
        assert r.status_code == 200, j
        assert len(j["session_token"]) > 100
        assert j["email_address"] == user_email

        h = login_and_make_session(
            client, user_email, mock_ses_client, valid_redirect_to_url
        )
        j = client.get("/api/v2/ooniauth/user-session", headers=h).json()
        assert j["is_logged_in"] == True
        assert j["role"] == "user"

    with freeze_time("1995-01-01"):
        r = client.post(f"/api/v2/ooniauth/user-session", json={"login_token": token})
        j = r.json()
        assert r.status_code != 200, j
