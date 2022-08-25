#
# Most of the private API runs statistics on the last N days. As such, tests
# are not deterministic.
#

import pytest


def privapi(client, subpath):
    response = client.get(f"/api/_/{subpath}")
    assert response.status_code == 200
    assert response.is_json
    return response.json


# TODO: improve tests


def test_private_api_asn_by_month(client):
    url = "asn_by_month"
    response = privapi(client, url)
    assert len(response) > 1
    r = response[0]
    assert sorted(r.keys()) == ["date", "value"]
    assert r["value"] > 10
    assert r["value"] < 10**6
    assert r["date"].endswith("T00:00:00+00:00")


def test_private_api_countries_by_month(client):
    url = "countries_by_month"
    response = privapi(client, url)
    assert len(response) > 1
    r = response[0]
    assert sorted(r.keys()) == ["date", "value"]
    assert r["value"] > 10
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
            assert a["count"] > 100
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


@pytest.mark.skip("FIXME not deterministic")
def test_private_api_website_networks(client, log):
    url = "website_networks?probe_cc=US"
    resp = privapi(client, url)
    assert len(resp["results"]) > 100


@pytest.mark.skip("FIXME not deterministic")
def test_private_api_website_stats(client, log):
    url = "website_stats?probe_cc=DE&probe_asn=3320&input=http:%2F%2Fwww.backtrack-linux.org%2F"
    resp = privapi(client, url)
    assert len(resp["results"]) > 2
    assert sorted(resp["results"][0].keys()) == [
        "anomaly_count",
        "confirmed_count",
        "failure_count",
        "test_day",
        "total_count",
    ]


@pytest.mark.skip("FIXME not deterministic")
def test_private_api_website_urls(client, log):
    url = "website_urls?probe_cc=US&probe_asn=209"
    response = privapi(client, url)
    r = response["metadata"]
    assert r["total_count"] > 0
    del r["total_count"]
    assert r == {
        "current_page": 1,
        "limit": 10,
        "next_url": "https://api.ooni.io/api/_/website_urls?limit=10&offset=10&probe_asn=209&probe_cc=US",
        "offset": 0,
    }
    assert len(response["results"]) == 10


def test_private_api_vanilla_tor_stats(client):
    url = "vanilla_tor_stats?probe_cc=BR"
    resp = privapi(client, url)
    assert "notok_networks" in resp
    return  # FIXME: implement tests with mocked db
    assert resp["notok_networks"] >= 0
    assert len(resp["networks"]) > 10
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


def test_private_api_im_networks(client):
    url = "im_networks?probe_cc=BR"
    resp = privapi(client, url)
    return  # FIXME: implement tests with mocked db
    assert len(resp) > 1
    assert len(resp["facebook_messenger"]["ok_networks"]) > 5
    if "telegram" in resp:
        assert len(resp["telegram"]["ok_networks"]) > 5
    assert len(resp["signal"]["ok_networks"]) > 5
    # assert len(resp["whatsapp"]["ok_networks"]) > 5


def test_private_api_im_stats_basic(client):
    url = "im_stats?probe_cc=CH&probe_asn=3303&test_name=facebook_messenger"
    resp = privapi(client, url)
    assert 20 < len(resp["results"]) < 34
    assert resp["results"][0]["total_count"] > -1
    assert resp["results"][0]["anomaly_count"] is None
    assert len(resp["results"][0]["test_day"]) == 25


@pytest.mark.skip("FIXME not deterministic")
def test_private_api_im_stats(client):
    url = "im_stats?probe_cc=CH&probe_asn=3303&test_name=facebook_messenger"
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
    assert resp["measurement_count"] > 1000
    assert resp["network_count"] > 10


def test_private_api_global_overview(client):
    url = "global_overview"
    response = privapi(client, url)
    assert "country_count" in response
    assert "measurement_count" in response
    assert "network_count" in response


def test_private_api_global_overview_by_month(client):
    url = "global_overview_by_month"
    resp = privapi(client, url)
    assert sorted(resp["networks_by_month"][0].keys()) == ["date", "value"]
    assert sorted(resp["countries_by_month"][0].keys()) == ["date", "value"]
    assert sorted(resp["measurements_by_month"][0].keys()) == ["date", "value"]
    assert resp["networks_by_month"][0]["date"].endswith("T00:00:00+00:00")


@pytest.mark.skip(reason="cannot be tested")
def test_private_api_quotas_summary(client):
    resp = privapi(client, "quotas_summary")


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


@pytest.mark.skip(reason="depends on fresh data")
def test_private_api_circumvention_stats_by_country(client, log):
    url = "circumvention_stats_by_country"
    resp = privapi(client, url)
    assert resp["v"] == 0
    assert len(resp["results"]) > 3


# # /circumvention_runtime_stats


@pytest.mark.skip(reason="depends on fresh data")
def test_private_api_circumvention_runtime_stats(client, log):
    url = "circumvention_runtime_stats"
    resp = privapi(client, url)
    assert resp["v"] == 0
    assert "error" not in resp, resp
    assert len(resp["results"]) > 3, resp
