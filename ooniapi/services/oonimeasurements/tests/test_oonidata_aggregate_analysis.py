import pytest

route = "api/v1/aggregation/analysis"
since = "2024-11-01"
until = "2024-11-10"


def test_oonidata_aggregation_analysis(client):
    response = client.get(route)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 0


def test_oonidata_aggregation_analysis_with_since_and_until(
    client, params_since_and_until_with_two_days
):
    response = client.get(route, params=params_since_and_until_with_two_days)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0

    for result in json["results"]:
        assert "domain" in result, result


@pytest.mark.parametrize(
    "filter_param, filter_value",
    [
        ("domain", "zh.wikipedia.org"),
        ("probe_cc", "IR"),
        ("probe_asn", 45758),
        ("test_name", "whatsapp"),
        ("input", "stun://stun.voys.nl:3478"),
        (
            "measurement_uid",
            "20241101233756.866609_TH_webconnectivity_1bf55fb5699c39ec",
        ),
    ],
)
def test_oonidata_aggregation_analysis_with_filters(
    client, filter_param, filter_value, params_since_and_until_with_ten_days
):
    params = params_since_and_until_with_ten_days
    params[filter_param] = filter_value

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[filter_param] == filter_value, result


def test_oonidata_aggregation_analysis_measurement_uid_only_skips_default_date_window(
    client,
):
    """
    Without measurement_uid, since/until default to the last 30 days (fixture data is older).

    With only measurement_uid, those defaults must not apply, so rows still match by
    measurement_uid even when their measurement_start_time falls outside the usual
    default window.
    """
    measurement_uid = "20241101233756.866609_TH_webconnectivity_1bf55fb5699c39ec"

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


def test_oonidata_aggregation_analysis_measurement_uid_with_explicit_since_and_until(
    client,
):
    """
    An explicit since/until must still be honored even when measurement_uid is set.
    """
    measurement_uid = "20241101233756.866609_TH_webconnectivity_1bf55fb5699c39ec"
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


def test_oonidata_aggregation_analysis_filtering_by_probe_asn_as_a_string_with_since_and_until(
    client, params_since_and_until_with_ten_days
):
    params = params_since_and_until_with_ten_days
    probe_asn = 45758
    params["probe_asn"] = "AS" + str(probe_asn)

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result["probe_asn"] == probe_asn, result


@pytest.mark.parametrize(
    "field",
    [
        "measurement_start_day",
        "domain",
        "probe_cc",
        "probe_asn",
        "test_name",
        "input",
    ],
)
def test_oonidata_aggregation_analysis_with_axis_x(
    client, field, params_since_and_until_with_ten_days
):
    params = params_since_and_until_with_ten_days
    params["axis_x"] = field

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[field] is not None, result


@pytest.mark.parametrize(
    "field",
    [
        "measurement_start_day",
        "domain",
        "probe_cc",
        "probe_asn",
        "test_name",
        "input",
    ],
)
def test_oonidata_aggregation_analysis_axis_y(
    client, field, params_since_and_until_with_ten_days
):
    params = params_since_and_until_with_ten_days
    params["axis_y"] = field

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[field] is not None, result


@pytest.mark.parametrize(
    "time_grain, total",
    [
        ("hour", 216),
        ("day", 9),
        ("week", 2),
        ("month", 1),
        ("year", 1),
        ("auto", 9),
    ],
)
def test_oonidata_aggregation_analysis_time_grain(
    client, time_grain, total, params_since_and_until_with_ten_days
):
    params = params_since_and_until_with_ten_days
    params["group_by"] = "timestamp"
    params["time_grain"] = time_grain

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == total
