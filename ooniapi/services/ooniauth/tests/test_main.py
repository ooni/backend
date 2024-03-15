import pytest

import httpx
from fastapi.testclient import TestClient
from ooniauth.main import lifespan, app, pkg_version
from ooniauth.common.config import Settings
from ooniauth.common.dependencies import get_settings


def test_index(client):
    r = client.get("/")
    j = r.json()
    assert r.status_code == 200


def test_version(client):
    r = client.get("/version")
    j = r.json()
    assert j["version"] == pkg_version
    assert len(j["package_name"]) > 1


def test_health_good(client):
    r = client.get("/health")
    j = r.json()
    assert j["status"] == "ok", j


def test_health_bad(client_with_bad_settings):
    r = client_with_bad_settings.get("/health")
    j = r.json()
    assert r.status_code != 200


def make_override_get_settings(**kw):
    def override_get_settings():
        return Settings(**kw)

    return override_get_settings


@pytest.mark.asyncio
async def test_lifecycle(prometheus_password):
    app.dependency_overrides[get_settings] = make_override_get_settings(
        prometheus_metrics_password=prometheus_password,
    )

    async with lifespan(app) as ls:
        client = TestClient(app)
        r = client.get("/metrics")
        assert r.status_code == 401

        auth = httpx.BasicAuth(username="prom", password=prometheus_password)
        r = client.get("/metrics", auth=auth)
        assert r.status_code == 200, r.text
