import pytest


route = "api/v1/measurements"


def test_list_measurements(client):
    response = client.get(route)
    json = response.json()

    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 100


def test_list_measurements_with_since_and_until(client):
    params = {
        "since": "2024-01-01",
        "until": "2024-01-02",
    }

    response = client.get(route, params=params)
    json = response.json()

    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 100


@pytest.mark.parametrize(
    "filter_param, filter_value",
    [
        ("test_name", "web_connectivity"),
        ("probe_cc", "IT"),
        ("probe_asn", "AS30722"),
    ]
)
def test_list_measurements_with_one_value_to_filters(client, filter_param, filter_value):
    params = {}
    params[filter_param] = filter_value

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[filter_param] == filter_value, result


def test_list_measurements_with_one_value_to_filters_not_present_in_the_result(client):
    domain = "cloudflare-dns.com"
    params = {
        "domain": domain,
    }

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert domain in result["input"], result


@pytest.mark.parametrize(
    "filter_param, filter_value",
    [
        ("test_name", "web_connectivity,dnscheck,stunreachability,tor"),
        ("probe_cc", "IT,US,RU"),
        ("probe_asn", "AS30722,3269,7738,55430"),
    ]
)
def test_list_measurements_with_multiple_values_to_filters(client, filter_param, filter_value):
    params = {}
    params[filter_param] = filter_value

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[filter_param] in filter_value, result


def test_list_measurements_with_multiple_values_to_filters_not_in_the_result(client):
    domainCollection = "cloudflare-dns.com, adblock.doh.mullvad.net, 1.1.1.1"
    params = {
        "domain": domainCollection
    }

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert any(domain in result["input"] for domain in domainCollection), result
