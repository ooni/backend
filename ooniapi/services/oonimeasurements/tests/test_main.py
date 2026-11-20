import httpx
import pytest
from fastapi.testclient import TestClient

from oonimeasurements.common.dependencies import get_settings

from .utils import get_postgresql_url


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
    assert r.status_code == 503


def test_health_postgresql_reachable(app, client, postgresql):
    settings = app.dependency_overrides[get_settings]()
    settings.postgresql_url = get_postgresql_url(postgresql)
    app.dependency_overrides[get_settings] = lambda: settings

    r = client.get("health")
    assert r.status_code == 200
    assert r.json()["warnings"] == []


def test_health_postgresql_unreachable(app, client):
    settings = app.dependency_overrides[get_settings]()
    settings.postgresql_url = "postgresql://bad:bad@localhost:1/bad"
    app.dependency_overrides[get_settings] = lambda: settings

    r = client.get("health")
    # Postgres being down doesn't fail the health check
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok", j
    assert j["warnings"] == ["postgresql_error"]


def test_metrics(app):
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 401

    auth = httpx.BasicAuth(username="prom", password="super_secure")
    r = client.get("/metrics", auth=auth)
    assert r.status_code == 200, r.text
