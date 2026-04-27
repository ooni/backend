import json
import zstd
import pytest
import ujson

from ..utils import get_msmt_hash


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

    upload_payload = {"format": "json", "content": {"test_keys": {}}}
    c = postj(client, f"/report/{rid}", upload_payload)
    expected_hash = get_msmt_hash(upload_payload)
    assert c["measurement_uid"].endswith(f"_IE_webconnectivity_{expected_hash}"), c

    c = postj(client, f"/report/{rid}/close", json={})
    assert c == {}, c


@pytest.mark.asyncio
async def test_collector_upload_msmt_valid_zstd(client):
    rid = "20230101T000000Z_integtest_IT_1_n1_integtest0000000"
    msmt_payload = {"test_keys": {}}
    zmsmt = zstd.compress(json.dumps(msmt_payload).encode())
    headers = [("Content-Encoding", "zstd")]
    c = post(client, f"/report/{rid}", zmsmt, headers=headers)
    assert len(c) == 1

    expected_hash = get_msmt_hash(msmt_payload)
    assert c["measurement_uid"].endswith(f"_IT_integtest_{expected_hash}"), c

@pytest.mark.asyncio
async def test_fastpath_fallback(client_with_mocked_fastpath):
    """When the first fastpath URL fails, the second one in the list
    should still receive the measurement.
    """
    client, mock_fastpath, success_url = client_with_mocked_fastpath

    rid = "20230101T000000Z_integtest_IT_1_n1_integtest0000000"
    msmt_payload = {
        "format": "json",
        "content": {
            "test_keys": {},
            "annotations": {"platform": "test_platform"},
            "software_name": "test_software",
            "software_version": "0.0.0",
        },
    }
    resp = client.post(f"/report/{rid}", json=msmt_payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "measurement_uid" in body, body
    msmt_uid = body["measurement_uid"]
    assert msmt_uid, body

    expected_hash = get_msmt_hash(msmt_payload)
    assert msmt_uid.endswith(f"_IT_integtest_{expected_hash}"), msmt_uid

    # check saved data
    expected_url = f"{success_url}/{msmt_uid}"
    assert list(mock_fastpath.uploads.keys()) == [expected_url]

    stored = ujson.loads(mock_fastpath.uploads[expected_url])
    assert get_msmt_hash(stored) == expected_hash
    assert stored["is_verified"] == "u"