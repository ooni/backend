from pathlib import Path
import json
import pytest


from ooniprobe.common.clickhouse_utils import insert_click


def getjson(client, url):
    response = client.get(url)
    assert response.status_code == 200
    assert response.is_json
    return response.json


def getjsonh(client, url, headers=None):
    response = client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.is_json
    return response.json


def post(client, url, data):
    response = client.post(url, data=data)
    assert response.status_code == 200
    return response.json()


def postj(client, url, **kw):
    response = client.post(url, json=kw)
    assert response.status_code == 200
    return response.json()


## Fixtures
@pytest.fixture
def load_url_priorities(clickhouse_db):
    path = Path("tests/fixtures/data")
    filename = "url_priorities_us.json"
    file = Path(path, filename)

    with file.open("r") as f:
        j = json.load(f)

    # 'sign' is created with default value 0, causing a db error.
    # use 1 to prevent it 
    for row in j:
        row["sign"] = 1

    query = "INSERT INTO url_priorities (sign, category_code, cc, domain, url, priority) VALUES"
    insert_click(clickhouse_db, query, j)


## Tests


def test_check_in_geoip(client):
    j = dict(
        on_wifi=True,
        charging=False,
    )
    headers = [
        ("X-Forwarded-For", "192.33.4.12")  # The IP address of c.root-servers.net
    ]
    c = client.post("/api/v1/check-in", json=j, headers=headers).json()
    assert c["probe_cc"] == "US"
    assert c["probe_asn"] == "AS2149"
    assert c["probe_network_name"] is not None


def test_check_in_basic(client, load_url_priorities):
    j = dict(
        probe_cc="US",
        probe_asn="AS1234",
        on_wifi=True,
        charging=False,
    )
    c = postj(client, "/api/v1/check-in", **j)

    assert c["v"] == 1
    urls = c["tests"]["web_connectivity"]["urls"]
    assert len(urls) > 1, urls

    webc_rid = c["tests"]["web_connectivity"]["report_id"]
    ts, stn, cc, asn_i, _coll, _rand = webc_rid.split("_")
    assert int(asn_i) == 1234
    assert stn == "webconnectivity"
    assert cc == "US"

    assert sorted(c["conf"]) == ["features", "test_helpers"]


def test_check_in_url_category_news(client):
    j = dict(
        on_wifi=True,
        charging=True,
        web_connectivity=dict(category_codes=["NEWS"]),
    )
    c = postj(client, "/api/v1/check-in", **j)
    assert c["v"] == 1
    urls = c["tests"]["web_connectivity"]["urls"]
    assert len(urls), urls
    for ui in urls:
        assert ui["category_code"] == "NEWS"

    webc_rid = c["tests"]["web_connectivity"]["report_id"]
    ts, stn, cc, asn_i, _coll, _rand = webc_rid.split("_")
    assert int(asn_i) == 0
    assert stn == "webconnectivity"
    assert cc == "ZZ"
