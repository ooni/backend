import json
import zstd
import pytest
from hashlib import sha512
import ujson
import copy

def postj(client, url, json):
    response = client.post(url, json=json)
    assert response.status_code == 200, response.json()
    return response.json()


def post(client, url, data, headers=None):
    response = client.post(url, data=data, headers=headers)
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_collector_open_report(client):
    j = {
        "data_format_version": "0.2.0",
        "format": "json",
        "probe_asn": "AS65550",  # reserved for examples
        "probe_cc": "IE",
        "software_name": "ooni-integ-test",
        "software_version": "0.0.0",
        "test_name": "web_connectivity",
        "test_start_time": "2020-09-09 14:11:11",
        "test_version": "0.1.0",
    }
    c = postj(client, "/report", j)
    rid = c.pop("report_id")
    assert "_webconnectivity_IE_65550_" in rid
    assert c == {
        "backend_version": "1.3.5",
        "supported_formats": ["yaml", "json"],
    }
    assert len(rid) == 61, rid


@pytest.mark.asyncio
async def test_collector_upload_msmt_bogus(client):
    # The path component is ignored, but a body without valid probe_cc /
    # probe_asn / test_name still has to be rejected.
    j = dict(format="json", content=dict(test_keys={}))
    resp = client.post("/report/bogus", json=j)
    assert resp.status_code == 400, resp


@pytest.mark.asyncio
async def test_collector_upload_msmt_valid(client):
    # open report, upload
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
    assert c == {
        "backend_version": "1.3.5",
        "supported_formats": ["yaml", "json"],
    }
    assert len(rid) == 61, rid

    upload_payload = {
        "format": "json",
        "content": {
            "test_keys": {},
            "probe_cc": "IE",
            "probe_asn": "AS34245",
            "test_name": "web_connectivity",
        },
    }
    c = postj(client, f"/report/{rid}", upload_payload)
    expected_hash = _get_hash_of(upload_payload)
    assert c["measurement_uid"].endswith(f"_IE_webconnectivity_{expected_hash}"), c

    c = postj(client, f"/report/{rid}/close", json={})
    assert c == {}, c


@pytest.mark.asyncio
async def test_collector_upload_msmt_valid_zstd(client):
    rid = "ignored-by-the-server"
    msmt_payload = {
        "format": "json",
        "content": {
            "test_keys": {},
            "probe_cc": "IT",
            "probe_asn": "AS1",
            "test_name": "integtest",
        },
    }
    zmsmt = zstd.compress(json.dumps(msmt_payload).encode())
    headers = [("Content-Encoding", "zstd")]
    c = post(client, f"/report/{rid}", zmsmt, headers=headers)
    assert "measurement_uid" in c, c

    expected_hash = _get_hash_of(msmt_payload)
    assert c["measurement_uid"].endswith(f"_IT_integtest_{expected_hash}"), c


def _get_hash_of(msmt: dict) -> str:
    payload = copy.deepcopy(msmt)
    payload["is_verified"] = "u"
    d = ujson.dumps(payload).encode()
    return sha512(d).hexdigest()[:16]