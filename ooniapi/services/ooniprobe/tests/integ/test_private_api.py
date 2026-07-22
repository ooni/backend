#
# Most of the private API runs statistics on the last N days. As such, tests
# are not deterministic.
#

import pytest
from urllib.parse import urljoin, urlencode

def privapi(client, subpath):
    response = client.get(f"/api/_/{subpath}")
    assert response.status_code == 200
    return response.json()


def test_private_api_asn_by_month(client, fixed_time):
    url = "asn_by_month"
    response = privapi(client, url)
    assert len(response) > 0, response
    r = response[0]
    assert sorted(r.keys()) == ["date", "value"]
    assert r["value"] >= 3
    assert r["value"] < 10**6
    assert r["date"].endswith("T00:00:00+00:00")


def test_private_api_countries_by_month(client, fixed_time):
    url = "countries_by_month"
    response = privapi(client, url)
    assert len(response) > 0, response

    for r in response:
        assert sorted(r.keys()) == ["date", "value"]
        assert r["value"] > 0
        assert r["value"] < 1000
        assert r["date"].endswith("T00:00:00+00:00")


def test_private_api_test_names(client, log):
    url = "test_names"
    response = privapi(client, url)
    assert response == {
        "test_names": [
            {"id": "bridge_reachability", "name": "Bridge Reachability"},
            {"id": "dash", "name": "DASH"},
            {"id": "dns_consistency", "name": "DNS Consistency"},
            {"id": "dnscheck", "name": "DNS Check"},
            {"id": "facebook_messenger", "name": "Facebook Messenger"},
            {
                "id": "http_header_field_manipulation",
                "name": "HTTP Header Field Manipulation",
            },
            {"id": "http_host", "name": "HTTP Host"},
            {"id": "http_invalid_request_line", "name": "HTTP Invalid Request Line"},
            {"id": "http_requests", "name": "HTTP Requests"},
            {"id": "meek_fronted_requests_test", "name": "Meek Fronted Requests"},
            {"id": "multi_protocol_traceroute", "name": "Multi Protocol Traceroute"},
            {"id": "ndt", "name": "NDT"},
            {"id": "psiphon", "name": "Psiphon"},
            {"id": "riseupvpn", "name": "RiseupVPN"},
            {"id": "signal", "name": "Signal"},
            {"id": "stunreachability", "name": "STUN Reachability"},
            {"id": "tcp_connect", "name": "TCP Connect"},
            {"id": "telegram", "name": "Telegram"},
            {"id": "tor", "name": "Tor"},
            {"id": "torsf", "name": "Tor Snowflake"},
            {"id": "urlgetter", "name": "URL Getter"},
            {"id": "vanilla_tor", "name": "Vanilla Tor"},
            {"id": "web_connectivity", "name": "Web Connectivity"},
            {"id": "whatsapp", "name": "WhatsApp"},
        ]
    }


def test_private_api_countries_total(client, log):
    url = "countries"
    response = privapi(client, url)
    assert "countries" in response
    assert len(response["countries"]) >= 20
    for a in response["countries"]:
        if a["alpha_2"] == "CA":
            assert a["count"] > 3
            assert a["name"] == "Canada"
            return

    assert 0, "CA not found"


def test_private_api_test_coverage(client, log):
    url = "test_coverage?probe_cc=BR"
    resp = privapi(client, url)
    assert 190 < len(resp["test_coverage"]) < 220
    assert 27 < len(resp["network_coverage"]) < 32
    assert sorted(resp["test_coverage"][0]) == ["count", "test_day", "test_group"]
    assert sorted(resp["network_coverage"][0]) == ["count", "test_day"]


def test_private_api_test_coverage_with_groups(client, log):
    url = "test_coverage?probe_cc=BR&test_groups=websites"
    resp = privapi(client, url)
    assert len(resp["test_coverage"]) > 10
    assert sorted(resp["test_coverage"][0]) == ["count", "test_day", "test_group"]
    assert 27 < len(resp["network_coverage"]) < 32


def test_private_api_domain_metadata1(client):
    url = "domain_metadata?domain=facebook.com"
    resp = privapi(client, url)
    assert resp["category_code"] == "GRP"
    assert resp["canonical_domain"] == "www.facebook.com"


def test_private_api_domain_metadata2(client):
    url = "domain_metadata?domain=www.facebook.com"
    resp = privapi(client, url)
    assert resp["category_code"] == "GRP"
    assert resp["canonical_domain"] == "www.facebook.com"


def test_private_api_domain_metadata3(client):
    url = "domain_metadata?domain=www.twitter.com"
    resp = privapi(client, url)
    assert resp["category_code"] == "GRP"
    assert resp["canonical_domain"] == "twitter.com"


def test_private_api_domain_metadata4(client):
    url = "domain_metadata?domain=www.this-domain-is-not-in-the-test-lists-for-sure.com"
    resp = privapi(client, url)
    assert resp["category_code"] == "MISC"
    exp = "this-domain-is-not-in-the-test-lists-for-sure.com"
    assert resp["canonical_domain"] == exp


def test_private_api_website_networks(client, log, fixed_time):
    url = "website_networks?probe_cc=US"
    resp = privapi(client, url)
    assert len(resp["results"]) == 19
    assert "count" in resp["results"][0]
    assert "probe_asn" in resp["results"][0]
    assert isinstance(resp["results"][0]["probe_asn"], int)
    assert isinstance(resp["results"][0]["count"], int)


def test_private_api_website_stats(client, log, fixed_time):
    url = urljoin("website_stats", "?" + urlencode({"probe_cc": "CN", "probe_asn": 9808, "input": "https://www.x.com"}))
    resp = privapi(client, url)
    assert len(resp["results"]) > 2
    assert sorted(resp["results"][0].keys()) == [
        "anomaly_count",
        "confirmed_count",
        "failure_count",
        "test_day",
        "total_count",
    ]


def test_private_api_website_urls(client, log, fixed_time):
    url = "website_urls?probe_cc=CN&probe_asn=9808"
    response = privapi(client, url)
    r = response["metadata"]
    assert r["total_count"] > 0
    del r["total_count"]
    assert r == {
        "current_page": 1,
        "limit": 10,
        "next_url": "https://testserver/api/_/website_urls?limit=10&offset=10&probe_asn=9808&probe_cc=CN",
        "offset": 0,
    }
    assert len(response["results"]) == 10


def test_private_api_vanilla_tor_stats(client, fixed_time):
    url = "vanilla_tor_stats?probe_cc=DE"
    resp = privapi(client, url)
    assert "notok_networks" in resp
    assert resp["notok_networks"] >= 0
    assert len(resp["networks"]) >= 9
    assert sorted(resp["networks"][0].keys()) == [
        "failure_count",
        "last_tested",
        "probe_asn",
        "success_count",
        "test_runtime_avg",
        "test_runtime_max",
        "test_runtime_min",
        "total_count",
    ]
    assert resp["last_tested"].startswith("20")


def test_private_api_vanilla_tor_stats_empty(client):
    url = "vanilla_tor_stats?probe_cc=XY"
    resp = privapi(client, url)
    assert resp["notok_networks"] == 0
    assert len(resp["networks"]) == 0
    assert resp["last_tested"] is None


def test_private_api_im_networks(client, fixed_time):
    url = "im_networks?probe_cc=DE"
    resp = privapi(client, url)
    assert len(resp["signal"]["ok_networks"]) == 5


def test_private_api_im_stats_basic(client):
    url = "im_stats?probe_cc=CH&probe_asn=3303&test_name=facebook_messenger"
    resp = privapi(client, url)
    assert 20 < len(resp["results"]) < 34
    assert resp["results"][0]["total_count"] > -1
    assert resp["results"][0]["anomaly_count"] is None
    assert len(resp["results"][0]["test_day"]) == 25


def test_private_api_im_stats(client, fixed_time):
    url = "im_stats?probe_cc=DE&probe_asn=680&test_name=signal"
    resp = privapi(client, url)
    assert len(resp["results"]) > 10
    assert resp["results"][0]["total_count"] > -1
    assert resp["results"][0]["anomaly_count"] is None
    assert len(resp["results"][0]["test_day"]) == 25
    assert sum(e["total_count"] for e in resp["results"]) > 0, resp


def test_private_api_network_stats(client):
    # TODO: the stats are not implemented
    url = "network_stats?probe_cc=GB"
    response = privapi(client, url)
    assert response == {
        "metadata": {
            "current_page": 1,
            "limit": 10,
            "next_url": None,
            "offset": 0,
            "total_count": 0,
        },
        "results": [],
    }


def test_private_api_country_overview(client):
    url = "country_overview?probe_cc=BR"
    resp = privapi(client, url)
    assert resp["first_bucket_date"].startswith("20"), resp
    assert resp["measurement_count"] > 1
    assert resp["network_count"] > 1


def test_private_api_global_overview(client):
    url = "global_overview"
    response = privapi(client, url)
    assert "country_count" in response
    assert "measurement_count" in response
    assert "network_count" in response


def test_private_api_global_overview_by_month(client, fixed_time):
    url = "global_overview_by_month"
    resp = privapi(client, url)
    assert sorted(resp["networks_by_month"][0].keys()) == ["date", "value"]
    assert sorted(resp["countries_by_month"][0].keys()) == ["date", "value"]
    assert sorted(resp["measurements_by_month"][0].keys()) == ["date", "value"]
    assert resp["networks_by_month"][0]["date"].endswith("T00:00:00+00:00")


def test_private_api_quotas_summary(client_with_admin_role):
    resp = privapi(client_with_admin_role, "quotas_summary")


def test_private_api_check_report_id(client, log):
    rid = "20210709T004340Z_webconnectivity_MY_4818_n1_YCM7J9mGcEHds2K3"
    url = f"check_report_id?report_id={rid}"
    response = privapi(client, url)
    assert response == {"v": 0, "found": True}


def test_private_api_check_bogus_report_id_is_found(client, log):
    # The API always returns True
    url = f"check_report_id?report_id=BOGUS_REPORT_ID"
    response = privapi(client, url)
    assert response == {"v": 0, "found": True}


# # /circumvention_stats_by_country


def test_private_api_circumvention_stats_by_country(client, log, fixed_time):
    url = "circumvention_stats_by_country"
    resp = privapi(client, url)
    assert resp["v"] == 0
    assert len(resp["results"]) > 3


# # /circumvention_runtime_stats


def test_private_api_circumvention_runtime_stats(client, log, fixed_time):
    url = "circumvention_runtime_stats"
    resp = privapi(client, url)
    assert resp["v"] == 0
    assert "error" not in resp, resp
    assert len(resp["results"]) > 3, resp


# # /asnmeta


def test_private_api_ansmeta(client, log):
    resp = privapi(client, "asnmeta?asn=0")
    assert resp == {"org_name": "Unknown"}


# # /networks


def test_private_api_networks(client, log):
    resp = privapi(client, "networks")
    assert resp["v"] == 0
    assert len(resp["results"]) > 50
    assert resp["results"][0]
    res = resp["results"][0]
    for k in ["cnt", "org_name", "probe_asn"]:
        assert k in res
    assert isinstance(res["probe_asn"], int)
    assert res["probe_asn"] > 0
    assert isinstance(res["cnt"], int)
    assert res["cnt"] > 0
    assert isinstance(res["org_name"], str)


# # /domains


def test_private_api_domains(client, log):
    resp = privapi(client, "domains")
    assert resp["v"] == 0
    rows = resp["results"]
    assert len(rows) > 5
    assert sorted(rows[0]) == ["category_code", "domain_name", "measurement_count"]
    d = {r["domain_name"]: r["category_code"] for r in rows}
    assert d["facebook.com"] == "GRP"
    assert d["ncac.org"] == "NEWS"
    assert d["twitter.com"] == "GRP"
