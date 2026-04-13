from typing import Any, Dict
import ooniauth_py
import pytest
from fastapi import status
from ooniauth_py import UserState, ServerState
from .utils import getj, make_submit_request, postj, setup_user

@pytest.mark.asyncio
async def test_manifest_basic(client, db):
    # Should not crash
    getj(client, "/api/v1/manifest")


@pytest.mark.asyncio
async def test_registration_basic(client):

    manifest = getj(client, "/api/v1/manifest")

    user_state = UserState(manifest['manifest']['public_parameters'])
    sign_req = user_state.make_registration_request()
    resp = postj(
        client,
        "/api/v1/sign_credential",
        {
            "credential_sign_request" : sign_req,
            "manifest_version" : manifest['meta']['version']
        }
    )
    # should be able to verify this credential
    user_state.handle_registration_response(resp['credential_sign_response']) # should not crash

@pytest.mark.asyncio
async def test_registration_errors(client):

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
        "manifest_version" : manifest['meta']['version']
    })

    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.content
    j = resp.json()
    assert j['detail']['error'] == 'protocol_error'

    # Changing random characters should mess with the serialization
    user = UserState(manifest['manifest']['public_parameters'])
    sign_req = user.make_registration_request()
    bad = "bad"
    assert len(sign_req) >= len(bad), sign_req
    sign_req = bad + sign_req[len(bad):]
    resp = client.post("/api/v1/sign_credential", json={
        "credential_sign_request" : sign_req,
        "manifest_version" : manifest['meta']['version']
    })

    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.content
    j = resp.json()
    assert j['detail']['error'] == 'deserialization_failed', j

@pytest.mark.asyncio
async def test_submission_basic(client):
    # open report
    j = make_report_request("IE", "AS34245")
    resp = postj(client, "/report", json=j)
    rid = resp.pop("report_id")

    # Create user
    user, manifest_version, emission_day = setup_user(client)

    submit_request = make_submit_request(user, "IE", "AS34245")

    msm = make_measurement(submit_request.nym, submit_request.request, manifest_version)

    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert 'is_verified' in c and c['is_verified'] is True, c

    assert c['submit_response'], "Submit response should not be null if the proof was verified"
    user.handle_submit_response(c['submit_response'])
    assert c["error"] is None


@pytest.mark.asyncio
async def test_submission_non_verified(client):
    """

    """
    j = make_report_request()
    resp = postj(client, "/report", json=j)
    rid = resp.pop("report_id")

    msm = {
        "format": "json",
        "content": {
            "test_name": "web_connectivity",
            "probe_asn": "AS34245",
            "probe_cc": "IE",
            "test_start_time": "2020-09-09 14:11:11",
        },
    }

    # no anoncred fields -> processed but not verified, no error
    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert c["verification_status"] == "unverified"
    assert c["submit_response"] is None
    assert c["error"] is None

    # unknown manifest -> processed but not verified, manifest error
    msm["manifest_version"] = "does-not-exist"
    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert c["verification_status"] == "failed"
    assert c["submit_response"] is None
    assert c["error"] == "manifest_not_found"

    # incomplete anoncred fields -> processed but not verified, incomplete-fields error
    user, manifest_version, _ = setup_user(client)
    msm["nym"] = "dummy-nym"
    msm["manifest_version"] = manifest_version
    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert c["verification_status"] == "failed"
    assert c["submit_response"] is None
    assert c["error"] == "incomplete_anonc_fields"

    # old protocol version -> protocol-version error
    submit_request = make_submit_request(user, "IE", "AS34245")
    msm["nym"] = submit_request.nym
    msm["zkp_request"] = submit_request.request
    msm["manifest_version"] = manifest_version
    msm["protocol_version"] = "0.0.1"
    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert c["verification_status"] == "failed"
    assert c["submit_response"] is None
    assert c["error"] == "protocol_version_too_old"

    # unparsable protocol version -> invalid protocol version error
    msm["protocol_version"] = "abc"
    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert c["verification_status"] == "failed"
    assert c["submit_response"] is None
    assert c["error"] == "invalid_protocol_version"

# TODO implement credential update
@pytest.mark.skip
@pytest.mark.asyncio
async def test_credential_update(client, client_with_original_manifest, second_manifest):

    (user, manifest, _) = client_with_original_manifest
    new_manifest = getj(client, "/api/v1/manifest")
    user.set_public_params(new_manifest["manifest"]["public_parameters"])
    result = postj(client, "/api/v1/update_credential", json=dict(
        old_manifest_version = manifest,
        manifest_version = new_manifest['meta']['version'],
        update_request = user.make_credential_update_request()
    ))
    assert 'update_response' in result
    user.handle_credential_update_response(result['update_response']) # should not crash

# TODO implement credential update
@pytest.mark.skip
@pytest.mark.asyncio
async def test_credential_update_with_submission(client, client_with_original_manifest, second_manifest):
    (user, manifest_version, emission_day) = client_with_original_manifest

    # first submit: should just work out of the box
    j = make_report_request()
    resp = postj(client, "/report", json=j)
    rid = resp.pop("report_id")

    submit_request = make_submit_request(user, "IE", "AS34245")

    msm = make_measurement(submit_request.nym, submit_request.request, manifest_version)

    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)

    assert c["verification_status"] == "verified"

    # second submit: should work after updating creds
    new_manifest = getj(client, "/api/v1/manifest")
    user.set_public_params(new_manifest['public_parameters'])
    result = postj(client, "/api/v1/update_credential", json=dict(
        old_manifest_version = manifest_version,
        manifest_version=new_manifest['meta']['version'],
        update_request = user.make_credential_update_request()
    ))

    assert 'update_response' in result
    user.handle_credential_update_response(result['update_response']) # should not crash

    j = make_report_request()
    resp = postj(client, "/report", json=j)
    rid = resp.pop("report_id")

    submit_request = make_submit_request(user, "IE", "AS34245")

    msm = make_measurement(submit_request.nym, submit_request.request, manifest_version)

    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)


def make_measurement(
    nym: str,
    zkp_request: str,
    manifest_version: str,
    probe_cc: str = "IE",
    probe_asn: str = "AS34245",
    protocol_version: str = ooniauth_py.get_protocol_version(),
) -> Dict[str, Any]:
    return {
        "format": "json",
        "content": {
            "test_name": "web_connectivity",
            "probe_asn": probe_asn,
            "probe_cc": probe_cc,
            "test_start_time": "2020-09-09 14:11:11",
        },
        "nym": nym,
        "zkp_request": zkp_request,
        "manifest_version": manifest_version,
        "protocol_version": protocol_version,
    }

def make_report_request(probe_cc: str = "IE", probe_asn: str = "AS34245") -> Dict[str, Any]:
    return {
        "data_format_version": "0.2.0",
        "format": "json",
        "probe_asn": probe_asn,
        "probe_cc": probe_cc,
        "software_name": "miniooni",
        "software_version": "0.17.0-beta",
        "test_name": "web_connectivity",
        "test_start_time": "2020-09-09 14:11:11",
        "test_version": "0.1.0",
    }
