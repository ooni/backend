import httpx
import pytest
from fastapi.testclient import TestClient


def test_health_good(client):
    r = client.get("health")
    j = r.json()
    assert j["status"] == "ok", j
    assert len(j["errors"]) == 0, j


def test_health_bad(client_with_bad_settings):
    r = client_with_bad_settings.get("health")
    j = r.json()
    print(j)
    assert j["status"] == "fail", j
    assert r.status_code == 200


def test_metrics(app):
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 401

    auth = httpx.BasicAuth(username="prom", password="super_secure")
    r = client.get("/metrics", auth=auth)
    assert r.status_code == 200, r.text
