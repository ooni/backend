from urllib.parse import parse_qs, urlparse
from ooniauth.common.utils import decode_jwt
from ooniauth.main import app
from freezegun import freeze_time


def register(client, email_address, mock_ses_client, valid_redirect_to_url):
    d = dict(email_address=email_address, redirect_to=valid_redirect_to_url)
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
    return token


def register_and_login(client, email_address, mock_ses_client, valid_redirect_to_url):
    token = register(
        client,
        email_address=email_address,
        mock_ses_client=mock_ses_client,
        valid_redirect_to_url=valid_redirect_to_url,
    )
    r = client.get(f"/api/v1/user_login?k={token}")
    j = r.json()
    assert r.status_code == 200, j
    assert j["redirect_to"] == valid_redirect_to_url
    assert "bearer" in j
    return {"Authorization": "Bearer " + j["bearer"]}


def test_login_user_bogus_token(client):
    r = client.get("/api/v1/user_login?k=BOGUS")
    assert r.status_code == 401
    # Note the key changed from "error" to "detail"
    assert r.json() == {"detail": "Invalid credentials"}


def test_user_register_non_valid_email(client, valid_redirect_to_url):
    d = dict(
        email_address="nick@localhost", redirect_to=valid_redirect_to_url
    )  # no FQDN
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 422
    j = r.json()
    assert j["detail"][0]["loc"] == ["body", "email_address"]


def test_user_register_non_valid_redirect(client, valid_redirect_to_url):
    d = dict(
        email_address="nick@a.org", redirect_to="https://BOGUS.example.com"
    )  # bogus fqdn
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 422

    d = dict(
        email_address="nick@a.org",
        redirect_to=valid_redirect_to_url.replace("https", "http"),
    )  # bogus fqdn
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 422


def test_user_register_missing_redirect(client, valid_redirect_to_url):
    d = dict(email_address="nick@a.org", redirect_to=valid_redirect_to_url)
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code == 200


def test_user_refresh(client, mock_ses_client, user_email, valid_redirect_to_url):
    r = client.get(
        "/api/v1/user_refresh_token", headers={"Authorization": "Bearer invalidtoken"}
    )
    assert r.status_code != 200
    j = r.json()
    print(j)

    h = register_and_login(client, user_email, mock_ses_client, valid_redirect_to_url)
    j = client.get("/api/_/account_metadata", headers=h).json()
    assert j["logged_in"] == True
    assert j["role"] == "user"

    j = client.get("/api/v1/user_refresh_token", headers=h).json()
    assert len(j["bearer"]) > 100


def test_user_register_and_refresh(
    client, mock_ses_client, user_email, valid_redirect_to_url
):
    j = client.get("/api/_/account_metadata").json()
    assert j["logged_in"] == False
    h = register_and_login(client, user_email, mock_ses_client, valid_redirect_to_url)
    j = client.get("/api/_/account_metadata", headers=h).json()
    assert j["logged_in"] == True
    assert j["role"] == "user"


def test_user_register_misconfigured_email(
    client, mock_misconfigured_ses_client, user_email, valid_redirect_to_url
):
    d = dict(email_address=user_email, redirect_to=valid_redirect_to_url)
    r = client.post("/api/v1/user_register", json=d)
    assert r.status_code != 200
    assert isinstance(mock_misconfigured_ses_client.send_email.side_effect, Exception)


def test_user_register_and_get_metadata(
    client, mock_ses_client, user_email, valid_redirect_to_url
):
    r = client.get("/api/_/account_metadata")
    j = r.json()
    assert j["logged_in"] == False
    h = register_and_login(client, user_email, mock_ses_client, valid_redirect_to_url)
    r = client.get("/api/_/account_metadata", headers=h)
    j = r.json()
    assert j["role"] == "user"
    assert j["logged_in"] == True


def test_admin_register_and_get_metadata(
    client, mock_ses_client, admin_email, valid_redirect_to_url
):
    r = client.get("/api/_/account_metadata")
    j = r.json()
    assert j["logged_in"] == False
    h = register_and_login(client, admin_email, mock_ses_client, valid_redirect_to_url)
    r = client.get("/api/_/account_metadata", headers=h)
    j = r.json()
    assert j["role"] == "admin"
    assert j["logged_in"] == True


def test_user_register_timetravel(
    client, mock_ses_client, user_email, valid_redirect_to_url
):
    with freeze_time("1990-01-01"):
        token = register(
            client,
            email_address=user_email,
            mock_ses_client=mock_ses_client,
            valid_redirect_to_url=valid_redirect_to_url,
        )
        r = client.get(f"/api/v1/user_login?k={token}")
        j = r.json()
        assert r.status_code == 200, j
        assert len(j["bearer"]) > 100
        assert j["email_address"] == user_email

        h = register_and_login(
            client, user_email, mock_ses_client, valid_redirect_to_url
        )
        j = client.get("/api/_/account_metadata", headers=h).json()
        assert j["logged_in"] == True
        assert j["role"] == "user"

    with freeze_time("1995-01-01"):
        r = client.get(f"/api/v1/user_login?k={token}")
        j = r.json()
        assert r.status_code != 200, j
