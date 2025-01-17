from typing import Dict
from ooniprobe.common import auth
from fastapi.testclient import TestClient


def test_register(client):
    c = _register(client)
    assert "client_id" in c
    assert len(c["client_id"]) == 132


def test_register_then_login(client, jwt_encryption_key):
    pwd = "HLdywVhzVCNqLvHCfmnMhIXqGmUFMTuYjmuGZhNlRTeIyvxeQTnjVJsiRkutHCSw"
    c = _register(client)
    assert "client_id" in c
    assert len(c["client_id"]) == 132

    tok = auth.decode_jwt(c["client_id"], audience="probe_login", key = jwt_encryption_key)

    client_id = c["client_id"]
    c = postj(client, "/api/v1/login", username=client_id, password=pwd)
    tok = auth.decode_jwt(c["token"], audience="probe_token", key = jwt_encryption_key)
    assert tok["registration_time"] is not None

    # Login with a bogus client id emulating probes before 2022
    client_id = "BOGUSBOGUS"
    j = dict(username=client_id, password=pwd)
    r = client.post("/api/v1/login", json=j)
    assert r.status_code == 200
    token = r.json()["token"]
    tok = auth.decode_jwt(token, audience="probe_token", key = jwt_encryption_key)
    assert tok["registration_time"] is None  # we don't know the reg. time

    # Expect failed login
    resp = client.post("/api/v1/login", json=dict())
    assert resp.status_code == 401

def test_update(client : TestClient, jwt_encryption_key):
    # Update will just say ok to anything you send, no matter
    # the data 

    # We can use whatever string for the client_id path parameter, 
    # but we use the login token to make sure that the returned token
    # works properly with the update endpoint
    c = _register(client)
    client_id = c["client_id"]
    c = postj(client, "/api/v1/login", username=client_id, password="some_pswd")
    token = c['token']

    data = _get_update_data()
    resp = client.put(f"/api/v1/update/{token}",json=data)
    assert resp.status_code == 200
    json = resp.json()
    assert "status" in json
    assert json['status'] == "ok"


def _get_update_data() -> Dict[str, str]:
    return {
		"probe_cc":            "IT",
		"probe_asn":           "AS1234",
		"platform":           "android",
		"software_name":       "ooni-testing",
		"software_version":    "0.0.1",
		"supported_tests":     "web_connectivity",
		"network_type":        "wifi",
		"available_bandwidth": "100",
		"language":           "en",
		"token":              "XXXX-TESTING",
		"password":           "testingPassword",
	}

def postj(client, url, **kw):
    response = client.post(url, json=kw)
    assert response.status_code == 200, f"Error: {response.content}"
    assert response.headers.get('content-type') == 'application/json'
    return response.json()

def _register(client):
    pwd = "HLdywVhzVCNqLvHCfmnMhIXqGmUFMTuYjmuGZhNlRTeIyvxeQTnjVJsiRkutHCSw"
    j = {
        "password": pwd,
        "platform": "miniooni",
        "probe_asn": "AS0",
        "probe_cc": "ZZ",
        "software_name": "miniooni",
        "software_version": "0.1.0-dev",
        "supported_tests": ["web_connectivity"],
    }
    return postj(client, "/api/v1/register", **j)