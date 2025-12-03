from typing import Tuple
from datetime import timedelta
from fastapi import status
from ooniprobe.models import OONIProbeServerState, OONIProbeManifest
from ooniprobe.dependencies import PostgresSessionDep
from ooniauth_py import UserState, ServerState
from .utils import getj, postj
import pytest

@pytest.fixture(scope="function")
def second_manifest(db: PostgresSessionDep):
    recent_manifest = OONIProbeManifest.get_latest(db)
    assert recent_manifest

    new_server_state = OONIProbeServerState.make_new_state(db)
    new_manifest = OONIProbeManifest(
        server_state_id = new_server_state.id,
        date_created = recent_manifest.date_created - timedelta(days=1)
        )

    db.add(new_manifest)
    db.commit()
    yield new_manifest
    db.delete(new_manifest)
    db.delete(new_server_state)
    db.commit()

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
        "probe_age_range": [emission_day - 30, emission_day + 1],
        "probe_msm_range": [0, 100],
        "manifest_version": manifest_version
    }
    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert c['is_verified'] == True  # noqa: E712

    assert c['submit_response'], "Submit response should not be null if the proof was verified"
    user.handle_submit_response(c['submit_response'])

def test_credential_update(client, second_manifest):
    user, manifest_version, emission_day = setup_user(client)
    old_server_state : OONIProbeServerState = second_manifest.server_state


def setup_user(client) -> Tuple[UserState, str, int]: # user, manifest version, emission day
    manifest = getj(client, "/api/v1/manifest")
    user = UserState(manifest['public_parameters'])
    req = user.make_registration_request()
    resp = postj(client, "/api/v1/sign_credential", json = {
        "credential_sign_request" : req,
        "manifest_version" : manifest['version']
    })
    user.handle_registration_response(resp['credential_sign_response'])

    return (user, manifest['version'], resp['emission_day'])