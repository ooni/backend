import pytest

from datetime import datetime
import httpx
import ooniauth_py
from fastapi.testclient import TestClient
from ooniprobe.main import app, lifespan
from ooniprobe.dependencies import (
    Manifest,
    ManifestMeta,
    ManifestResponse,
    Match,
    Policy,
    PolicyEntry,
)
import ooniprobe.main as m

def fake_get_manifest(s3, bucket, key):
    return ManifestResponse(
        manifest=Manifest(
            submission_policy=[
                PolicyEntry(
                    match=Match(probe_cc="*", probe_asn="*"),
                    policy=Policy(age=(2461110, 2826140), measurement_count=(0, 10000000)),
                )
            ],
            public_parameters="public parameters"
            ),
        meta = ManifestMeta(
            version="1",
            last_modification_date=datetime.now(),
            manifest_url="https://ooni.mock/manifest",
            library_version=ooniauth_py.__version__,
            protocol_version=ooniauth_py.get_protocol_version(),
        )
    )

@pytest.mark.asyncio
async def test_health_good(client, monkeypatch):
    monkeypatch.setattr(m, "get_manifest", fake_get_manifest)
    r = client.get("health")
    j = r.json()
    assert j["status"] == "ok", j
    assert len(j["errors"]) == 0, j


def test_health_bad(client_with_bad_settings):
    r = client_with_bad_settings.get("health")
    j = r.json()
    assert j["status"] == "fail", j
    assert len(j["errors"]) > 0, j


@pytest.mark.asyncio
async def test_metrics(client):
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
