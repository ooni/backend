import pytest

import httpx
from fastapi.testclient import TestClient
from ooniprobe.main import lifespan, app


def test_health_good(client):
    r = client.get("health")
    j = r.json()
    assert j["status"] == "ok", j
    assert len(j["errors"]) == 0, j


def test_health_bad(client_with_bad_settings):
    r = client_with_bad_settings.get("health")
    j = r.json()
    assert j["status"] == "fail", j
    assert len(j["errors"]) > 0, j


def test_metrics(client):
    r = client.get("/metrics")


@pytest.mark.asyncio
async def test_lifecycle(test_settings):
    settings = test_settings()
    async with lifespan(app, settings, repeating_tasks_active=False) as ls:
        client = TestClient(app)
        r = client.get("/metrics")
        assert r.status_code == 401

        auth = httpx.BasicAuth(username="prom", password="super_secure")
        r = client.get("/metrics", auth=auth)
        assert r.status_code == 200, r.text
