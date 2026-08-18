import pytest

route = "api/v1/aggregation/observations"


def test_oonidata_aggregation_observations(client):
    response = client.get(route)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 0


def test_oonidata_aggregation_observations_with_since_and_until(
    client, params_since_and_until_with_two_days
):
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
        (
            "measurement_uid",
            "20241101233410.169530_DE_webconnectivity_2eb2a331c9ce0630",
        ),
    ],
)
def test_oonidata_aggregation_observations_with_filters(
    client, filter_name, filter_value, params_since_and_until_with_ten_days
):
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


def test_oonidata_aggregation_observations_measurement_uid_only_skips_default_date_window(
    client,
):
    """
    Without measurement_uid, since/until default to the last 30 days (fixture data is older).

    With only measurement_uid, those defaults must not apply, so rows still match by
    measurement_uid even when their measurement_start_time falls outside the usual
    default window.
    """
    measurement_uid = "20241101233410.169530_DE_webconnectivity_2eb2a331c9ce0630"

    default_response = client.get(route)
    assert default_response.status_code == 200
    assert len(default_response.json()["results"]) == 0

    by_uid = client.get(route, params={"measurement_uid": measurement_uid})
    assert by_uid.status_code == 200
    j = by_uid.json()
    assert isinstance(j["results"], list), j
    assert len(j["results"]) > 0
    for result in j["results"]:
        assert result["measurement_uid"] == measurement_uid, result


def test_oonidata_aggregation_observations_measurement_uid_with_explicit_since_and_until(
    client,
):
    """
    An explicit since/until must still be honored even when measurement_uid is set.
    """
    measurement_uid = "20241101233410.169530_DE_webconnectivity_2eb2a331c9ce0630"
    params = {
        "measurement_uid": measurement_uid,
        # This range does not cover the measurement's date (2024-11-01).
        "since": "2025-01-01",
        "until": "2025-01-02",
    }

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 0


@pytest.mark.parametrize(
    "time_grain, total",
    [
        ("hour", 215),
        ("day", 9),
        ("week", 2),
        ("month", 1),
        ("year", 1),
        ("auto", 9),
    ],
)
def test_oonidata_aggregation_observations_time_grain(
    client, time_grain, total, params_since_and_until_with_ten_days
):
    params = params_since_and_until_with_ten_days
    params["group_by"] = "timestamp"
    params["time_grain"] = time_grain

    response = client.get(route, params=params)

    json = response.json()
    assert len(json["results"]) == total


def test_oonidata_aggregation_observations_groupby_failure(
    client, params_since_and_until_with_two_days
):
    params = params_since_and_until_with_two_days
    params["group_by"] = ["failure", "timestamp"]

    response = client.get(route, params=params)

    json = response.json()
    assert len(json["results"]) == 24
    first_result = json["results"][0]
    assert "failure" in first_result.keys()
    assert "timestamp" in first_result.keys()
    assert "observation_count" in first_result.keys()
