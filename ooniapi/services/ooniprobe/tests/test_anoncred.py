from datetime import datetime
from typing import Any, Dict
from httpx import Client
from fastapi import status
from ooniprobe.models import OONIProbeServerState
from ooniprobe.common.routers import ISO_FORMAT_DATETIME

def getj(client : Client, url: str, params: Dict[str, Any] = {}) -> Dict[str, Any]:
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK, f"Unexpected status code: {resp.status_code}. {resp.content}"
    return resp.json()

def test_manifest_basic(client, db):
    latest = OONIProbeServerState.get_latest(db)
    assert latest is not None, "Server state not initialized"

    m = getj(client, "/api/v1/manifest")
    assert latest.public_parameters == m['public_parameters']
    assert datetime.strftime(latest.date_created, ISO_FORMAT_DATETIME) == m['date_created']
