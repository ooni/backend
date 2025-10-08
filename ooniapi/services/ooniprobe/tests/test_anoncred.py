from datetime import datetime
from typing import Any, Dict
from httpx import Client
from fastapi import status
from ooniprobe.models import OONIProbeServerState
from ooniprobe.common.routers import ISO_FORMAT_DATETIME
from ooniauth_py import UserState

def getj(client : Client, url: str, params: Dict[str, Any] = {}) -> Dict[str, Any]:
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK, f"Unexpected status code: {resp.status_code}. {resp.content}"
    return resp.json()

def postj(client : Client, url: str, json: Dict[str, Any] | None = None) -> Dict[str, Any]:
    resp = client.post(url, json=json)
    assert resp.status_code == status.HTTP_200_OK, f"Unexpected status code: {resp.status_code}. {resp.content}"
    return resp.json()

def test_manifest_basic(client, db):
    latest = OONIProbeServerState.get_latest(db)
    assert latest is not None, "Server state not initialized"

    m = getj(client, "/api/v1/manifest")
    assert latest.public_parameters == m['public_parameters']
    assert datetime.strftime(latest.date_created, ISO_FORMAT_DATETIME) == m['date_created']

def test_registration_basic(client):

    manifest = getj(client, "/api/v1/manifest")

    user_state = UserState(manifest['public_parameters'])
    sign_req = user_state.make_registration_request()
    resp = postj(
        client,
        "/api/v1/sign_credential",
        {
            "credential_sign_request" : sign_req,
            "manifest_date_created" : manifest['date_created']
        }
    )
    # should be able to verify this credential
    user_state.handle_registration_response(resp['credential_sign_response']) # should not crash
