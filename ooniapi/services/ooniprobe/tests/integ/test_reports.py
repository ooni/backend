import json
import zstd


def postj(client, url, json):
    response = client.post(url, json=json)
    assert response.status_code == 200, response.json()
    return response.json()


def post(client, url, data, headers=None):
    response = client.post(url, data=data, headers=headers)
    assert response.status_code == 200
    return response.json()


def test_collector_open_report(client):
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


def test_collector_upload_msmt_bogus(client):
    j = dict(format="json", content=dict(test_keys={}))
    resp = client.post("/report/bogus", json=j)
    assert resp.status_code == 400, resp


def test_collector_upload_msmt_valid(client):
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

    msmt = dict(test_keys={})
    c = postj(client, f"/report/{rid}", {"format":"json", "content":msmt}) # unsure about this merge
    assert c['measurement_uid'].endswith("_IE_webconnectivity_e7889aeba0b36729"), c

    c = postj(client, f"/report/{rid}/close", json={})
    assert c == {}, c


def test_collector_upload_msmt_valid_zstd(client):
    rid = "20230101T000000Z_integtest_IT_1_n1_integtest0000000"
    msmt = json.dumps(dict(test_keys={})).encode()
    zmsmt = zstd.compress(msmt)
    headers = [("Content-Encoding", "zstd")]
    c = post(client, f"/report/{rid}", zmsmt, headers=headers)
    assert len(c) == 1
    assert c['measurement_uid'].endswith("_IT_integtest_50be3cd5406bca65"), c
