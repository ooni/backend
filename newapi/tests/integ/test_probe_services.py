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

import os
import pytest


@pytest.fixture()
def log(app):
    return app.logger


@pytest.fixture(autouse=True, scope="session")
def setup_database_url():
    os.environ["DATABASE_URL"] = "postgresql://readonly@localhost:5432/metadb"


def getjson(client, url):
    response = client.get(url)
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


# @pytest.mark.skip(reason="TODO")
# def test_(client):
#     c = getjson(client, "/")
#     assert True


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
    urls = c["tests"]["web_connectivity"]["urls"]
    assert len(urls) == 20, urls

    webc_rid = c["tests"]["web_connectivity"]["report_id"]
    ts, stn, cc, asn_i, _coll, _rand = webc_rid.split("_")
    assert int(asn_i) == 1234
    assert stn == "webconnectivity"
    assert cc == "US"


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


## Test /api/v1/collectors


def test_list_collectors(client):
    c = getjson(client, "/api/v1/collectors")
    assert len(c) == 6


# @pytest.mark.skip(reason="TODO")
# def test_(client):
#     print(dir(client))
#     c = post(client, "/api/v1/login")
#     assert True


# def test_register(client):
#    j = {
#        "password": "HLdywVhzVCNqLvHCfmnMhIXqGmUFMTuYjmuGZhNlRTeIyvxeQTnjVJsiRkutHCSw",
#        "platform": "miniooni",
#        "probe_asn": "AS0",
#        "probe_cc": "ZZ",
#        "software_name": "miniooni",
#        "software_version": "0.1.0-dev",
#        "supported_tests": ["web_connectivity"],
#    }
#    c = postj(client, "/api/v1/register", **j)
#    print(c)
#    assert 0


def test_test_helpers(client):
    c = getjson(client, "/api/v1/test-helpers")
    assert len(c) == 6


# @pytest.mark.skip(reason="TODO")
# def test_psiphon(client):
#     c = getjson(client, "/api/v1/test-list/psiphon-config")
#     assert True


# @pytest.mark.skip(reason="TODO")
# def test_tor_targets(client):
#     c = getjson(client, "/api/v1/test-list/tor-targets")
#     assert True


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
        "probe_asn": "AS34245",
        "probe_cc": "IE",
        "software_name": "miniooni",
        "software_version": "0.17.0-beta",
        "test_name": "web_connectivity",
        "test_start_time": "2020-09-09 14:11:11",
        "test_version": "0.1.0",
    }
    c = postj(client, "/report", **j)
    rid = c.pop("report_id")
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
    c = postj(client, "/report", **j)
    rid = c.pop("report_id")
    assert c == {
        "backend_version": "1.3.5",
        "supported_formats": ["yaml", "json"],
    }
    assert len(rid) == 61, rid

    msmt = dict(test_keys={})
    c = postj(client, f"/report/{rid}", format="json", content=msmt)
    assert c == {}

    c = postj(client, f"/report/{rid}/close")
    assert c == {}


def test_collector_close_report(client):
    c = postj(client, "/report/TestReportID/close")
    assert c == {}


# Test-list related tests


def test_url_prioritization(client):
    c = getjson(client, "/api/v1/test-list/urls?limit=100")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 100,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }

    assert len(set(r["url"] for r in c["results"])) == 100


def test_url_prioritization_category_code(client):
    c = getjson(client, "/api/v1/test-list/urls?category_codes=NEWS&limit=100")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 100,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["category_code"] == "NEWS"

    assert len(set(r["url"] for r in c["results"])) == 100


def test_url_prioritization_category_codes(client):
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


def test_url_prioritization_country_code_limit(client):
    c = getjson(client, "/api/v1/test-list/urls?country_code=US&limit=999")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 999,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["country_code"] in ("XX", "US")

    assert len(set(r["url"] for r in c["results"])) == 999


def test_url_prioritization_country_code_nolimit(client):
    c = getjson(client, "/api/v1/test-list/urls?country_code=US")
    assert "metadata" in c
    xx_cnt = 0
    for r in c["results"]:
        assert r["country_code"] in ("XX", "US")
        if r["country_code"] == "XX":
            xx_cnt += 1

    assert xx_cnt > 1200
    us_cnt = c["metadata"]["count"] - xx_cnt
    assert us_cnt > 40
