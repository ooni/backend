from ..utils import getj, postj

## Tests
def test_check_in_geoip(client):
    j = dict(
        on_wifi=True,
        charging=False,
    )
    headers = {
        "X-Forwarded-For":"192.33.4.12"  # The IP address of c.root-servers.net
    }

    c = postj(client, "/api/v1/check-in", json=j, headers=headers)

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
    c = postj(client, "/api/v1/check-in", j)

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
    c = postj(client, "/api/v1/check-in", j)
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


def test_test_helpers(client):
    c = getj(client, "/api/v1/test-helpers")
    assert len(c) == 6
