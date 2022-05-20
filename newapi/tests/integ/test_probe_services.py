"""
Integration test for Probe Services API

Warning: this test runs against a real database
See README.adoc

Lint using:
    black -t py37 -l 100 --fast ooniapi/tests/integ/test_probe_services.py

Test using:
    pytest-3 -s --show-capture=no ooniapi/tests/integ/test_probe_services.py
"""

# TODO: mock out /etc/ooni/api.conf during testing

from mock import patch
from pathlib import Path
import json

import pytest

import ooniapi.probe_services


@pytest.fixture()
def log(app):
    return app.logger


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
    assert response.is_json
    return response.json


def postj(client, url, **kw):
    response = client.post(url, json=kw)
    assert response.status_code == 200
    assert response.is_json
    return response.json


def test_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert not resp.is_json
    assert "Welcome to" in resp.data.decode()


# # Follow the order in ooniapi/probe_services.py


## Test /api/v1/check-in


def mock_load_json():
    known = ("/etc/ooni/tor_targets.json", "/etc/ooni/psiphon_config.json")

    def load_json(fn):
        if fn in known:
            f = Path("tests/integ/data") / Path(fn).name
            print(f"    Mocking probe_services._load_json {fn} -> {f}")
            return json.loads(f.read_text())
        raise NotImplementedError(f"Unexpected fname to be mocked out: {fn}")

    return load_json


def test_check_in_basic(client):
    j = dict(
        probe_cc="US",
        probe_asn="AS1234",
        on_wifi=True,
        charging=False,
    )
    with patch("ooniapi.probe_services._load_json", new_callable=mock_load_json):
        c = postj(client, "/api/v1/check-in", **j)

    assert c["v"] == 1
    urls = c["tests"]["web_connectivity"]["urls"]
    assert len(urls) > 1, urls

    webc_rid = c["tests"]["web_connectivity"]["report_id"]
    ts, stn, cc, asn_i, _coll, _rand = webc_rid.split("_")
    assert int(asn_i) == 1234
    assert stn == "webconnectivity"
    assert cc == "US"

    # psiphon and tor configurations
    assert sorted(c["conf"]) == ["psiphon", "tor"]


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


@pytest.mark.skip("Not supported. TODO: remove?")
def test_check_in_url_category_code_passed_as_string(client, citizenlab_tblready):
    # category_codes should be sent as an array, but comma-separated string
    # is handled anyways
    j = dict(
        web_connectivity=dict(category_codes="NEWS,HUMR"),
    )
    c = postj(client, "/api/v1/check-in", **j)
    assert c["v"] == 1
    urls = c["tests"]["web_connectivity"]["urls"]
    assert len(urls), urls
    for ui in urls:
        assert ui["category_code"] in ("NEWS", "HUMR")


def test_check_in_url_prioritization_category_codes(client, citizenlab_tblready):
    c = getjson(
        client,
        "/api/v1/test-list/urls?category_codes=NEWS,HUMR&country_code=US&limit=100",
    )
    assert "metadata" in c
    assert c["metadata"]["count"]
    c["metadata"]["count"] = "ignored"
    assert c["metadata"] == {
        "count": "ignored",
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["category_code"] in ("NEWS", "HUMR")

    assert set(r["url"] for r in c["results"])

def test_check_in_geoip(client):
    j = dict(
        on_wifi=True,
        charging=False,
    )
    headers = [
        ('X-Forwarded-For', '192.33.4.12') # The IP address of c.root-servers.net
    ]
    c = client.post("/api/v1/check-in", json=j, headers=headers).json
    assert c["probe_cc"] == "US"
    assert c["probe_asn"] == "AS2149"
    assert c["probe_network_name"] is not None

# # Test /api/v1/collectors


def test_list_collectors(client):
    c = getjson(client, "/api/v1/collectors")
    assert len(c) == 6


# # Probe authentication


def _register(client):
    pwd = "HLdywVhzVCNqLvHCfmnMhIXqGmUFMTuYjmuGZhNlRTeIyvxeQTnjVJsiRkutHCSw"
    j = {
        "password": pwd,
        "platform": "miniooni",
        "probe_asn": "AS0",
        "probe_cc": "ZZ",
        "software_name": "miniooni",
        "software_version": "0.1.0-dev",
        "supported_tests": ["web_connectivity"],
    }
    return postj(client, "/api/v1/register", **j)


import ooniapi.auth


def decode_token(client):
    # Decode JWT token in the cookie jar
    assert len(client.cookie_jar) == 1
    cookie = list(client.cookie_jar)[0].value
    tok = ooniapi.auth.decode_jwt(cookie, audience="user_auth")
    return tok


def test_register(client):
    c = _register(client)
    assert "client_id" in c
    assert len(c["client_id"]) == 132


def test_register_then_login(client):
    pwd = "HLdywVhzVCNqLvHCfmnMhIXqGmUFMTuYjmuGZhNlRTeIyvxeQTnjVJsiRkutHCSw"
    c = _register(client)
    assert "client_id" in c
    assert len(c["client_id"]) == 132
    tok = ooniapi.auth.decode_jwt(c["client_id"], audience="probe_login")

    client_id = c["client_id"]
    c = postj(client, "/api/v1/login", username=client_id, password=pwd)
    tok = ooniapi.auth.decode_jwt(c["token"], audience="probe_token")
    assert tok["registration_time"] is not None

    # Login with a bogus client id emulating probes before 2022
    client_id = "BOGUSBOGUS"
    j = dict(username=client_id, password=pwd)
    r = client.post("/api/v1/login", json=j)
    assert r.status_code == 200
    token = r.json["token"]
    tok = ooniapi.auth.decode_jwt(token, audience="probe_token")
    assert tok["registration_time"] is None  # we don't know the reg. time

    # Expect failed login
    resp = client.post("/api/v1/login", json=dict())
    # FIXME assert resp.status_code == 401


def test_test_helpers(client):
    c = getjson(client, "/api/v1/test-helpers")
    assert len(c) == 6


@patch("ooniapi.probe_services._load_json")
def test_psiphon(mock_load_json, client):

    # register and login
    pwd = "HLdywVhzVCNqLvHCfmnMhIXqGmUFMTuYjmuGZhNlRTeIyvxeQTnjVJsiRkutHCSw"
    client_id = _register(client)["client_id"]

    c = postj(client, "/api/v1/login", username=client_id, password=pwd)
    tok = ooniapi.auth.decode_jwt(c["token"], audience="probe_token")
    assert tok["registration_time"] is not None

    url = "/api/v1/test-list/psiphon-config"
    # broken token
    headers = {"Authorization": "Bearer " + c["token"][2:]}
    r = client.get(url, headers=headers)
    assert r.status_code == 401

    mock_load_json.return_value = {"a": "b"}

    # valid token
    headers = {"Authorization": "Bearer " + c["token"]}
    r = client.get(url, headers=headers)
    assert r.status_code == 200, r.json
    assert r.json == {"a": "b"}


@patch("ooniapi.probe_services._load_json")
def test_tor_targets(mock_load_json, client):
    # register and login
    pwd = "HLdywVhzVCNqLvHCfmnMhIXqGmUFMTuYjmuGZhNlRTeIyvxeQTnjVJsiRkutHCSw"
    client_id = _register(client)["client_id"]

    c = postj(client, "/api/v1/login", username=client_id, password=pwd)
    tok = ooniapi.auth.decode_jwt(c["token"], audience="probe_token")
    assert tok["registration_time"] is not None

    url = "/api/v1/test-list/tor-targets"
    # broken token
    headers = {"Authorization": "Bearer " + c["token"][2:]}
    r = client.get(url, headers=headers)
    assert r.status_code == 401

    mock_load_json.return_value = {"a": "b"}

    # valid token
    headers = {"Authorization": "Bearer " + c["token"]}
    r = client.get(url, headers=headers)
    assert r.status_code == 200, r.json
    assert r.json == {"a": "b"}


def test_bouncer_net_tests(client):
    j = {
        "net-tests": [
            {
                "input-hashes": None,
                "name": "web_connectivity",
                "test-helpers": ["web-connectivity"],
                "version": "0.0.1",
            }
        ]
    }
    c = postj(client, "/bouncer/net-tests", **j)
    expected = {
        "net-tests": [
            {
                "collector": "httpo://guegdifjy7bjpequ.onion",
                "collector-alternate": [
                    {"type": "https", "address": "https://ams-pg.ooni.org"},
                    {
                        "front": "dkyhjv0wpi2dk.cloudfront.net",
                        "type": "cloudfront",
                        "address": "https://dkyhjv0wpi2dk.cloudfront.net",
                    },
                ],
                "name": "web_connectivity",
                "test-helpers": {
                    "tcp-echo": "37.218.241.93",
                    "http-return-json-headers": "http://37.218.241.94:80",
                    "web-connectivity": "httpo://y3zq5fwelrzkkv3s.onion",
                },
                "test-helpers-alternate": {
                    "web-connectivity": [
                        {"type": "https", "address": "https://wcth.ooni.io"},
                        {
                            "front": "d33d1gs9kpq1c5.cloudfront.net",
                            "type": "cloudfront",
                            "address": "https://d33d1gs9kpq1c5.cloudfront.net",
                        },
                    ]
                },
                "version": "0.0.1",
                "input-hashes": None,
            }
        ]
    }
    assert c == expected


def test_bouncer_net_tests_bad_request1(client):
    resp = client.post("/bouncer/net-tests")
    assert resp.status_code == 400


def test_bouncer_net_tests_bad_request2(client):
    j = {"net-tests": []}
    resp = client.post("/bouncer/net-tests", json=j)
    assert resp.status_code == 400


# # test collector


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
    c = postj(client, "/report", **j)
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


def test_collector_close_report(client):
    c = postj(client, "/report/TestReportID/close")
    assert c == {}


# Test-list related tests are in test_prioritization.py
