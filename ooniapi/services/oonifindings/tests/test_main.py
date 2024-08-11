import pytest

import httpx
from fastapi.testclient import TestClient
from oonifindings.main import lifespan, app


def test_health_good(client):
    r = client.get("health")
    j = r.json()
    assert j["status"] == "ok", j
    assert len(j["errors"]) == 0, j


# TODO(decfox): have a stronger health check test
def test_health_bad(client_with_bad_settings):
    r = client_with_bad_settings.get("health")
    j = r.json()
    assert r.status_code == 200
    assert j["status"] == "fail", j


def test_metrics(client):
    client.get("/metrics")


@pytest.mark.asyncio
async def test_lifecycle():
    async with lifespan(app):
        client = TestClient(app)
        r = client.get("/metrics")
        assert r.status_code == 401

        auth = httpx.BasicAuth(username="prom", password="super_secure")
        r = client.get("/metrics", auth=auth)
        assert r.status_code == 200, r.text
