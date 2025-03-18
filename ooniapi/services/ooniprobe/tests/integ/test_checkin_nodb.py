from pathlib import Path
import pytest
import json

## Test /api/v1/check-in


def test_check_in(client):
    j = dict(
        probe_cc="US",
        probe_asn="AS1234",
        on_wifi=True,
        charging=False,
    )
    c = postj(client, "/api/v1/check-in", **j)
    assert c["v"] == 1
    assert c["utc_time"].startswith("20")
    assert c["utc_time"].endswith("Z")
    assert "T" in c["utc_time"]
    assert len(c["utc_time"]) == 20
    urls = c["tests"]["web_connectivity"]["urls"]
    assert len(urls) == 20, urls

    webc_rid = c["tests"]["web_connectivity"]["report_id"]
    ts, stn, cc, asn_i, _coll, _rand = webc_rid.split("_")
    assert int(asn_i) == 1234
    assert stn == "webconnectivity"
    assert cc == "US"

    # psiphon and tor configurations
    assert sorted(c["conf"]) == ["features", "psiphon", "tor"]


def test_check_in_url_category_news(client):
    j = dict(
        on_wifi=True,
        charging=True,
        web_connectivity=dict(category_codes=["NEWS"]),
    )
    c = postj(client, "/api/v1/check-in", **j)
    assert c["v"] == 1
    urls = c["tests"]["web_connectivity"]["urls"]
    assert len(urls) == 100, urls
    for ui in urls:
        assert ui["category_code"] == "NEWS"

    webc_rid = c["tests"]["web_connectivity"]["report_id"]
    ts, stn, cc, asn_i, _coll, _rand = webc_rid.split("_")
    assert int(asn_i) == 0
    assert stn == "webconnectivity"
    assert cc == "ZZ"


def test_check_in_url_category_multi(client):
    j = dict(
        probe_cc="IT",
        on_wifi=True,
        charging=True,
        web_connectivity=dict(category_codes=["NEWS", "MILX", "FILE"]),
    )
    c = postj(client, "/api/v1/check-in", **j)
    assert c["v"] == 1
    urls = c["tests"]["web_connectivity"]["urls"]
    assert len(urls) == 100, urls
    d = {}
    for u in urls:
        cco = u["category_code"]
        if cco not in d:
            d[cco] = 0
        d[cco] += 1

    assert d == {"FILE": 10, "MILX": 3, "NEWS": 87}
    webc_rid = c["tests"]["web_connectivity"]["report_id"]
    ts, stn, cc, asn_i, _coll, _rand = webc_rid.split("_")
    assert int(asn_i) == 0
    assert stn == "webconnectivity"
    # assert cc == "ZZ"


@pytest.mark.skip(reason="broken")
def test_check_in_url_category_code_passed_as_string(client):
    # category_codes should be sent as an array, but comma-separated string
    # is handled anyways
    j = dict(
        web_connectivity=dict(category_codes="NEWS,HUMR"),
    )
    c = postj(client, "/api/v1/check-in", **j)
    assert c["v"] == 1
    urls = c["tests"]["web_connectivity"]["urls"]
    assert len(urls) == 100, urls
    for ui in urls:
        assert ui["category_code"] in ("NEWS", "HUMR")


def test_check_in_url_prioritization_category_codes(client):
    c = getjson(
        client,
        "/api/v1/test-list/urls?category_codes=NEWS,HUMR&country_code=US&limit=100",
    )
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 100,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["category_code"] in ("NEWS", "HUMR")

    assert len(set(r["url"] for r in c["results"])) == 100


def test_check_in_geoip(client):
    j = dict(
        on_wifi=True,
        charging=False,
    )
    headers = [
        ("X-Forwarded-For", "192.33.4.12")  # The IP address of c.root-servers.net
    ]
    resp = client.post("/api/v1/check-in", json=j, headers=headers)
    assert resp.status_code == 200, f"Error {resp.json()}"
    c = resp.json()
    assert c["probe_cc"] == "US"
    assert c["probe_asn"] == "AS2149"
    assert c["probe_network_name"] is not None

def postj(client, url, **kw):
    response = client.post(url, json=kw)
    assert response.status_code == 200
    return response.json()

def getjson(client, url):
    response = client.get(url)
    assert response.status_code == 200
    return response.json()