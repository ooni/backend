from datetime import datetime
from typing import Any, Dict
from httpx import Client
from fastapi import status
from ooniprobe.models import OONIProbeServerState
from ooniprobe.common.routers import ISO_FORMAT_DATETIME
from ooniauth_py import UserState, ServerState

def getj(client : Client, url: str, params: Dict[str, Any] = {}) -> Dict[str, Any]:
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK, f"Unexpected status code: {resp.status_code}. {resp.content}"
    return resp.json()

def postj(client : Client, url: str, json: Dict[str, Any] | None = None, headers: Dict[str, Any] | None = None) -> Dict[str, Any]:
    resp = client.post(url, json=json, headers=headers)
    assert resp.status_code == status.HTTP_200_OK, f"Unexpected status code: {resp.status_code}. {resp.content}"
    return resp.json()

def post(client, url, data, headers=None):
    response = client.post(url, data=data, headers=headers)
    assert response.status_code == 200
    return response.json()

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

def test_registration_errors(client):

    bad_date = datetime.strftime(datetime(2012, 12, 21), ISO_FORMAT_DATETIME)
    resp = client.post("/api/v1/sign_credential",
                       json={
                            "credential_sign_request" : "doesntmatter",
                            "manifest_date_created" : bad_date
                        }
                    )
    # Bad manifest date should raise 404
    assert resp.status_code == 404, resp.content
    j = resp.json()
    assert 'error' in j['detail'] and 'message' in j['detail'], j
    assert j['detail']['error'] == "manifest_not_found"

    # Not using the right public params should not verify
    manifest = getj(client, "/api/v1/manifest")
    bad_server = ServerState()
    user = UserState(bad_server.get_public_parameters())
    resp = client.post("/api/v1/sign_credential", json={
        "credential_sign_request" : user.make_registration_request(),
        "manifest_date_created" : manifest['date_created']
    })

    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.content
    j = resp.json()
    assert j['detail']['error'] == 'protocol_error'

    # Changing random characters should mess with the serialization
    user = UserState(manifest['public_parameters'])
    sign_req = user.make_registration_request()
    bad = "bad"
    assert len(sign_req) >= len(bad), sign_req
    sign_req = bad + sign_req[len(bad):]
    resp = client.post("/api/v1/sign_credential", json={
        "credential_sign_request" : sign_req,
        "manifest_date_created" : manifest['date_created']
    })

    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.content
    j = resp.json()
    assert j['detail']['error'] == 'deserialization_failed', j

def test_submission_basic(client):
    # open report
    j = {
        "data_format_version": "0.2.0",
        "format": "json",
        "probe_asn": "AS34245",
        "probe_cc": "IE",
        "software_name": "miniooni",
        "software_version": "0.17.0-beta",
        "test_name": "web_connectivity",
        "test_start_time": "2020-09-09 14:11:11",
        "test_version": "0.1.0",
    }
    c = postj(client, "/report", json=j)
    rid = c.pop("report_id")
    msmt = dict(test_keys={}, probe_cc = "VE", asn = "AS1234", test_name = "web_connectivity")
    c = postj(client, f"/api/v1/submit_measurement/{rid}", {"format":"json", "content":msmt})
    assert c == {}
