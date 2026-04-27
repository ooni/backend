from typing import Any, Dict
import ooniauth_py
import pytest
import ujson
from fastapi import status
from ooniauth_py import UserState, ServerState
from pydantic import ValidationError
from ooniprobe.dependencies import Manifest, Match, Policy, PolicyEntry
from ooniprobe.routers.v1.probe_services import get_ranges_from_policy
from .utils import get_msmt_hash, getj, make_submit_request, postj, setup_user

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
    assert c["verification_status"] == "verified", c

    assert c['submit_response'], "Submit response should not be null if the proof was verified"
    user.handle_submit_response(c['submit_response'])
    assert c["error"] is None


@pytest.mark.asyncio
async def test_fastpath_fallback(client_with_mocked_fastpath):
    """
    When the first fastpath URL fails, the second one in the list should
    still receive a verified anonymous-credentials measurement.
    """
    client, mock_fastpath, success_url = client_with_mocked_fastpath

    # open report
    j = make_report_request("IE", "AS34245")
    resp = postj(client, "/report", json=j)
    rid = resp.pop("report_id")

    # build a verifiable submission
    user, manifest_version, _ = setup_user(client)
    submit_request = make_submit_request(user, "IE", "AS34245")
    msm = make_measurement(submit_request.nym, submit_request.request, manifest_version)

    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert c["verification_status"] == "verified", c
    assert c["error"] is None, c
    assert c["submit_response"], (
        "submit_response should not be null when verification succeeded"
    )
    msmt_uid = c["measurement_uid"]
    assert msmt_uid, c

    # Verified anonymous-credential submissions inject "t" as the
    # `is_verified` flag in the stored payload before hashing.
    expected_hash = get_msmt_hash(msm, is_verified="t")
    assert msmt_uid.endswith(f"_IE_webconnectivity_{expected_hash}"), msmt_uid

    # Check response bytes
    expected_url = f"{success_url}/{msmt_uid}"
    assert list(mock_fastpath.uploads.keys()) == [expected_url]

    stored = ujson.loads(mock_fastpath.uploads[expected_url])
    assert get_msmt_hash(stored, is_verified="t") == expected_hash
    assert stored["is_verified"] == "t"


@pytest.mark.asyncio
async def test_fastpath_only_submits_once_on_success(client_with_two_working_fastpaths):
    """
    When the first fastpath URL succeeds, the receiver should stop iterating
    """
    client, mock_fastpath, first_url, second_url = client_with_two_working_fastpaths

    # open report
    j = make_report_request("IE", "AS34245")
    resp = postj(client, "/report", json=j)
    rid = resp.pop("report_id")

    # build a verifiable submission
    user, manifest_version, _ = setup_user(client)
    submit_request = make_submit_request(user, "IE", "AS34245")
    msm = make_measurement(submit_request.nym, submit_request.request, manifest_version)

    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert c["verification_status"] == "verified", c
    assert c["error"] is None, c
    msmt_uid = c["measurement_uid"]
    assert msmt_uid, c

    # Sanity-check the bytes that were forwarded to the fastpath
    expected_hash = get_msmt_hash(msm, is_verified="t")
    assert msmt_uid.endswith(f"_IE_webconnectivity_{expected_hash}"), msmt_uid

    # Only the first fastpath URL should have received the measurement
    expected_url = f"{first_url}/{msmt_uid}"
    assert list(mock_fastpath.uploads.keys()) == [expected_url], (
        "measurement should be forwarded to the first fastpath URL only, "
        f"got {list(mock_fastpath.uploads.keys())}"
    )


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
    assert c["verification_status"] == "unverified"
    assert c["submit_response"] is None
    assert c["error"] == "manifest_not_found"

    # incomplete anoncred fields -> processed but not verified, incomplete-fields error
    user, manifest_version, _ = setup_user(client)
    msm["nym"] = "dummy-nym"
    msm["manifest_version"] = manifest_version
    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert c["verification_status"] == "unverified"
    assert c["submit_response"] is None
    assert c["error"] == "incomplete_anonc_fields"

    # old protocol version -> protocol-version error
    submit_request = make_submit_request(user, "IE", "AS34245")
    msm["nym"] = submit_request.nym
    msm["zkp_request"] = submit_request.request
    msm["manifest_version"] = manifest_version
    msm["protocol_version"] = "0.0.1"
    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert c["verification_status"] == "unverified"
    assert c["submit_response"] is None
    assert c["error"] == "protocol_version_too_old"

    # unparsable protocol version -> invalid protocol version error
    msm["protocol_version"] = "abc"
    c = postj(client, f"/api/v1/submit_measurement/{rid}", msm)
    assert c["verification_status"] == "unverified"
    assert c["submit_response"] is None
    assert c["error"] == "invalid_protocol_version"


def test_get_ranges_from_policy_match_precedence():
    policy = [
        PolicyEntry(
            match=Match(probe_asn="AS15704", probe_cc="ES"),
            policy=Policy(age=(9, 10), measurement_count=(90, 100)),
        ),
        PolicyEntry(
            match=Match(probe_asn="*", probe_cc="ES"),
            policy=Policy(age=(7, 8), measurement_count=(70, 80)),
        ),
        PolicyEntry(
            match=Match(probe_asn="AS15704", probe_cc="*"),
            policy=Policy(age=(5, 6), measurement_count=(50, 60)),
        ),
        PolicyEntry(
            match=Match(probe_asn="*", probe_cc="*"),
            policy=Policy(age=(3, 4), measurement_count=(30, 40)),
        ),
    ]

    age_range, msm_range = get_ranges_from_policy(policy, "ES", "AS15704")
    assert age_range == (9, 10)
    assert msm_range == (90, 100)

    age_range, msm_range = get_ranges_from_policy(policy, "ES", "AS99999")
    assert age_range == (7, 8)
    assert msm_range == (70, 80)

    age_range, msm_range = get_ranges_from_policy(policy, "IT", "AS15704")
    assert age_range == (5, 6)
    assert msm_range == (50, 60)

    age_range, msm_range = get_ranges_from_policy(policy, "IT", "AS99999")
    assert age_range == (3, 4)
    assert msm_range == (30, 40)

    no_catchall_policy = [
        PolicyEntry(
            match=Match(probe_asn="AS15704", probe_cc="ES"),
            policy=Policy(age=(9, 10), measurement_count=(90, 100)),
        )
    ]
    with pytest.raises(ValueError, match="No matching submission_policy entry"):
        get_ranges_from_policy(no_catchall_policy, "VE", "AS8048")


def test_get_ranges_from_policy_uses_wildcard_match():
    policy = [
        PolicyEntry(
            match=Match(probe_asn="*", probe_cc="*"),
            policy=Policy(age=(11, 12), measurement_count=(110, 120)),
        )
    ]
    age_range, msm_range = get_ranges_from_policy(policy, "BR", "AS28573")
    assert age_range == (11, 12)
    assert msm_range == (110, 120)


def test_get_ranges_from_policy_requires_matching_entry():
    with pytest.raises(ValueError, match="No matching submission_policy entry"):
        get_ranges_from_policy([], "FR", "AS3215")

def test_policy_entry_requires_both_ranges():
    with pytest.raises(ValidationError):
        Policy.model_validate({"age": [21, 22]})


def test_get_ranges_from_policy_first_match_wins():
    policy = [
        PolicyEntry(
            match=Match(probe_asn="*", probe_cc="*"),
            policy=Policy(age=(1, 1), measurement_count=(1, 1)),
        ),
        PolicyEntry(
            match=Match(probe_asn="AS1234", probe_cc="IT"),
            policy=Policy(age=(9, 9), measurement_count=(9, 9)),
        ),
    ]
    age_range, msm_range = get_ranges_from_policy(policy, "IT", "AS1234")
    assert age_range == (1, 1)
    assert msm_range == (1, 1)


def _manifest_from_payload(payload):
    manifest_payload = {
        "nym_scope": "ooni.org/{probe_cc}/{probe_asn}",
        "public_parameters": "public parameters",
        **payload,
    }
    manifest_raw = ujson.dumps(manifest_payload)
    manifest_json = ujson.loads(manifest_raw)
    return Manifest(**manifest_json)


def test_manifest_parsing_preserves_important_fields():
    manifest = _manifest_from_payload(
        {
            "submission_policy": [
                {
                    "match": {"probe_cc": "*", "probe_asn": "*"},
                    "policy": {
                        "age": [2461110, 2826140],
                        "measurement_count": [0, 10000000],
                    },
                }
            ]
        }
    )
    assert manifest.nym_scope == "ooni.org/{probe_cc}/{probe_asn}"
    assert manifest.public_parameters == "public parameters"
    assert len(manifest.submission_policy) == 1
    entry = manifest.submission_policy[0]
    assert entry.match.probe_cc == "*"
    assert entry.match.probe_asn == "*"
    assert entry.policy.age == (2461110, 2826140)
    assert entry.policy.measurement_count == (0, 10000000)


def test_manifest_rejects_ranges_with_invalid_length():
    with pytest.raises(ValidationError):
        _manifest_from_payload(
            {
                "submission_policy": [
                    {
                        "match": {"probe_cc": "*", "probe_asn": "*"},
                        "policy": {
                            "age": [2461110],
                            "measurement_count": [0, 10000000],
                        },
                    }
                ]
            }
        )
    with pytest.raises(ValidationError):
        _manifest_from_payload(
            {
                "submission_policy": [
                    {
                        "match": {"probe_cc": "*", "probe_asn": "*"},
                        "policy": {"age": [2461110, 2826140], "measurement_count": [0]},
                    }
                ]
            }
        )


def test_manifest_requires_probe_cc_and_probe_asn():
    with pytest.raises(ValidationError):
        _manifest_from_payload(
            {
                "submission_policy": [
                    {
                        "match": {"probe_cc": "*"},
                        "policy": {
                            "age": [2461110, 2826140],
                            "measurement_count": [0, 10000000],
                        },
                    }
                ]
            }
        )
    with pytest.raises(ValidationError):
        _manifest_from_payload(
            {
                "submission_policy": [
                    {
                        "match": {"probe_asn": "*"},
                        "policy": {
                            "age": [2461110, 2826140],
                            "measurement_count": [0, 10000000],
                        },
                    }
                ]
            }
        )


def test_manifest_rejects_missing_or_bad_types_for_policy_and_match():
    with pytest.raises(ValidationError):
        _manifest_from_payload(
            {"submission_policy": [{"match": {"probe_cc": "*", "probe_asn": "*"}}]}
        )
    with pytest.raises(ValidationError):
        _manifest_from_payload(
            {
                "submission_policy": [
                    {
                        "policy": {
                            "age": [2461110, 2826140],
                            "measurement_count": [0, 10000000],
                        }
                    }
                ]
            }
        )
    with pytest.raises(ValidationError):
        _manifest_from_payload({"submission_policy": "not-a-list"})
    with pytest.raises(ValidationError):
        _manifest_from_payload(
            {
                "submission_policy": [
                    {
                        "match": "not-a-dict",
                        "policy": {
                            "age": [2461110, 2826140],
                            "measurement_count": [0, 10000000],
                        },
                    }
                ]
            }
        )


def test_manifest_requires_catch_all_rule():
    with pytest.raises(
        ValidationError, match="Last rule in submission policy should be a catch-all."
    ):
        _manifest_from_payload(
            {
                "submission_policy": [
                    {
                        "match": {"probe_cc": "IT", "probe_asn": "AS1234"},
                        "policy": {
                            "age": [2461110, 2826140],
                            "measurement_count": [0, 10000000],
                        },
                    }
                ]
            }
        )


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
