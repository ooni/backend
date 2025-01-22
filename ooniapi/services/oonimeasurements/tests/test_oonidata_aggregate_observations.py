import pytest

route = "api/v1/aggregation/observations"


def test_oonidata_aggregation_observations(client):
    response = client.get(route)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 0


def test_oonidata_aggregation_observations_with_since_and_until(client, params_since_and_until_with_two_days):
    response = client.get(route, params=params_since_and_until_with_two_days)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0

    for result in json["results"]:
        assert "observation_count" in result, result
        assert "failure" in result, result


@pytest.mark.parametrize(
    "filter_name, filter_value",
    [
        ("probe_cc", "IT"),
        ("probe_asn", 45758),
        ("probe_asn", [45758, 5650]),
        ("test_name", "whatsapp"),
        ("hostname", "www.on-instant.com"),
        ("ip", "64.233.190.139"),
    ]
)
def test_oonidata_aggregation_observations_with_filters(client, filter_name, filter_value, params_since_and_until_with_ten_days):
    params = params_since_and_until_with_ten_days
    params[filter_name] = filter_value

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        if isinstance(filter_value, list):
            assert result[filter_name] in filter_value, result
        else:
            assert result[filter_name] == filter_value, result


@pytest.mark.parametrize(
    "time_grain, total",
    [
        ("hour", 215),
        ("day", 9),
        ("week", 2),
        ("month", 1),
        ("year", 1),
        ("auto", 9),
    ]
)
def test_oonidata_aggregation_observations_time_grain(client, time_grain, total, params_since_and_until_with_ten_days):
    params = params_since_and_until_with_ten_days
    params["group_by"] = "timestamp"
    params["time_grain"] = time_grain

    response = client.get(route, params=params)

    json = response.json()
    assert len(json["results"]) == total
