from urllib.parse import urlencode

import pytest


def api(client, subpath, **kw):
    url = f"/api/v1/{subpath}"
    if kw:
        assert "?" not in url
        url += "?" + urlencode(kw)

    response = client.get(url)
    assert response.status_code == 200
    assert response.is_json
    return response.json


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_torsf_stats_cc(client, log):
    url = "torsf_stats?probe_cc=IT&since=2021-07-28&until=2021-07-29"
    r = api(client, url)
    assert r["result"] == [
        {
            "anomaly_count": 0,
            "anomaly_rate": 0.0,
            "failure_count": 0,
            "measurement_count": 2,
            "measurement_start_day": "2021-07-29",
            "probe_cc": "IT",
        }
    ]


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_torsf_stats_nocc(client, log):
    url = "torsf_stats?&since=2021-07-28&until=2021-07-29"
    r = api(client, url)
    assert r["result"] == [
        {
            "anomaly_count": 0,
            "anomaly_rate": 0.0,
            "failure_count": 0,
            "measurement_count": 2,
            "measurement_start_day": "2021-07-29",
            "probe_cc": "IT",
        }
    ]
