from datetime import datetime
from typing import Any, Dict, Tuple
from httpx import Client
from fastapi import status
from ooniprobe.models import OONIProbeServerState, OONIProbeManifest
from ooniprobe.common.routers import ISO_FORMAT_DATETIME
from ooniauth_py import UserState, ServerState

def getj(client : Client, url: str, params: Dict[str, Any] = {}) -> Dict[str, Any]:
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK, f"Unexpected status code: {resp.status_code} - {url}. {resp.content}"
    return resp.json()

def postj(client : Client, url: str, json: Dict[str, Any] | None = None, headers: Dict[str, Any] | None = None) -> Dict[str, Any]:
    resp = client.post(url, json=json, headers=headers)
    assert resp.status_code == status.HTTP_200_OK, f"Unexpected status code: {resp.status_code} - {url}. {resp.content}"
    return resp.json()

def post(client, url, data, headers=None):
    response = client.post(url, data=data, headers=headers)
    assert response.status_code == 200
    return response.json()

def test_manifest_basic(client, db):
    latest = db.query(OONIProbeServerState).limit(1).one_or_none()
    manifest = OONIProbeManifest.get_latest(db)
    assert latest is not None, "Server state not initialized"
    assert manifest is not None, "Manifest not initialized"

    m = getj(client, "/api/v1/manifest")

    assert latest.public_parameters == m['public_parameters']
    assert manifest.version == m['version']

def test_registration_basic(client):

    manifest = getj(client, "/api/v1/manifest")

    user_state = UserState(manifest['public_parameters'])
    sign_req = user_state.make_registration_request()
    resp = postj(
        client,
        "/api/v1/sign_credential",
        {
            "credential_sign_request" : sign_req,
            "manifest_version" : manifest['version']
        }
    )
    # should be able to verify this credential
    user_state.handle_registration_response(resp['credential_sign_response']) # should not crash

def test_registration_errors(client):

    bad_version = "999"
    resp = client.post("/api/v1/sign_credential",
                       json={
                            "credential_sign_request" : "doesntmatter",
                            "manifest_version" : bad_version
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
        "manifest_version" : manifest['version']
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
        "manifest_version" : manifest['version']
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
    resp = postj(client, "/report", json=j)
    rid = resp.pop("report_id")

    # Create user
    user, manifest_version, emission_day = setup_user(client)

    submit_request = user.make_submit_request("IE", "AS34245", emission_day)
    msm = {
        "format": "json",
        "content": {
            "test_name": "web_connectivity",
            "probe_asn": "AS34245",
            "probe_cc": "IE",
            "test_start_time": "2020-09-09 14:11:11",
        },
        "nym": submit_request.nym,
        "zkp_request": submit_request.request,
        "age_range": [emission_day - 30, emission_day + 1],
        "msm_range": [0, 10],
        "manifest_version": manifest_version
    }
    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert c == {'is_verified' : True, "measurement_uid" : rid}

def setup_user(client) -> Tuple[UserState, str, int]: # user, manifest version
    manifest = getj(client, "/api/v1/manifest")
    user = UserState(manifest['public_parameters'])
    req = user.make_registration_request()
    resp = postj(client, "/api/v1/sign_credential", json = {
        "credential_sign_request" : req,
        "manifest_version" : manifest['version']
    })
    user.handle_registration_response(resp['credential_sign_response'])

    return (user, manifest['version'], resp['emission_day'])