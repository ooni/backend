import pytest

from ooniprobe.common import auth

ENDPOINTS = ["/api/v1/test-list/tor-targets", "/api/v1/test-list/psiphon-config"]


def probe_token(key, aud="probe_token"):
    return auth.create_jwt({"registration_time": None, "aud": aud}, key=key)


@pytest.mark.parametrize("url", ENDPOINTS)
def test_requires_token(client, url):
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("url", ENDPOINTS)
@pytest.mark.parametrize(
    "authorization",
    ["Bearer", "Bearer notajwt", "Basic Zm9vOmJhcg=="],
)
def test_rejects_malformed_token(client, url, authorization):
    r = client.get(url, headers={"Authorization": authorization})
    assert r.status_code == 401


@pytest.mark.parametrize("url", ENDPOINTS)
def test_rejects_wrong_audience(client, url, jwt_encryption_key):
    tok = probe_token(jwt_encryption_key, aud="probe_login")
    r = client.get(url, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


@pytest.mark.parametrize("url", ENDPOINTS)
def test_rejects_wrong_key(client, url):
    tok = probe_token("not-the-server-key")
    r = client.get(url, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


@pytest.mark.parametrize("url", ENDPOINTS)
def test_accepts_login_token(client, url):
    reg = client.post(
        "/api/v1/register",
        json={
            "password": "x" * 64,
            "platform": "miniooni",
            "probe_asn": "AS0",
            "probe_cc": "ZZ",
            "software_name": "miniooni",
            "software_version": "0.1.0-dev",
            "supported_tests": ["web_connectivity"],
        },
    ).json()
    login = client.post(
        "/api/v1/login", json={"username": reg["client_id"], "password": "x" * 64}
    ).json()
    r = client.get(url, headers={"Authorization": f"Bearer {login['token']}"})
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
