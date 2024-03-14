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


admin_e = "integtest@openobservatory.org"
user_e = "admin+dev@ooni.org"


def test_login_user_bogus_token(client):
    r = client.get("/api/v1/user_login?k=BOGUS")
    assert r.status_code == 401
    # Note the key changed from "error" to "detail"
    assert r.json() == {"detail": "Invalid credentials"}


def test_user_register_non_valid_email(client):
    d = dict(
        email_address="nick@localhost", redirect_to="https://explorer.ooni.org"
    )  # no FQDN
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 422
    j = r.json()
    assert j["detail"][0]["loc"] == ["body", "email_address"]


def test_user_register_non_valid_redirect(client):
    d = dict(
        email_address="nick@a.org", redirect_to="https://BOGUS.ooni.org"
    )  # bogus fqdn
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 422


def test_user_register_missing_redirect(client):
    d = dict(email_address="nick@a.org")
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 200


def _register_and_login(client, email_address, mock_ses_client):
    d = dict(email_address=email_address, redirect_to="https://explorer.ooni.org")
    r = client.post("/api/v1/user_register", json=d)
    j = r.json()
    assert r.status_code == 200
    assert j == {"msg": "ok"}

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

    r = client.get(f"/api/v1/user_login?k={token}")
    j = r.json()
    assert r.status_code == 200, j
    assert j["redirect_to"] == "https://explorer.ooni.org"
    assert "bearer" in j
    return {"Authorization": "Bearer " + j["bearer"]}


def test_user_register_and_logout(client, mock_ses_client):
    j = client.get("/api/_/account_metadata").json()
    assert j["logged_in"] == False
    h = _register_and_login(client, user_e, mock_ses_client)
    j = client.get("/api/_/account_metadata", headers=h).json()
    assert j == {"logged_in": True, "role": "user"}  # logged in
    # simulate logout by not using the token in variable "h"
    j = client.get("/api/_/account_metadata").json()
    assert j["logged_in"] == False


def test_user_register_and_get_metadata(client, mock_ses_client):
    r = client.get("/api/_/account_metadata")
    j = r.json()
    assert j["logged_in"] == False
    h = _register_and_login(client, user_e, mock_ses_client)
    r = client.get("/api/_/account_metadata", headers=h)
    j = r.json()
    assert j["role"] == "user"
    assert j["logged_in"] == True

    h = _register_and_login(client, user_e, mock_ses_client)
