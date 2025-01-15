import pytest

route = "api/v1/aggregation/analysis"
since = "2024-11-01"
until = "2024-11-10"


def test_oonidata_aggregation_analysis(client):
    response = client.get(route)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 0


def test_oonidata_aggregation_analysis_with_since_and_until(client):
    response = client.get(f"{route}?since={since}&until={until}")

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0

    for result in json["results"]:
        assert "anomaly_count" in result, result
        assert "domain" in result, result


@pytest.mark.parametrize(
    "filter_param, filter_value",
    [
        ("domain", "zh.wikipedia.org"),
        ("probe_cc", "IR"),
        ("probe_asn", 45758),
        ("test_name", "whatsapp"),
        ("input", "stun://stun.voys.nl:3478"),
    ]
)
def test_oonidata_aggregation_analysis_with_filters(client, filter_param, filter_value):
    params = {
        "since": since,
        "until": until
    }
    params[filter_param] = filter_value

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[filter_param] == filter_value, result


def test_oonidata_aggregation_analysis_filtering_by_probe_asn_as_a_string_with_since_and_until(client):
    probe_asn = 45758
    probe_asn_as_a_string =  "AS" + str(probe_asn)

    response = client.get(f"{route}?probe_asn={probe_asn_as_a_string}&since={since}&until={until}")

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result["probe_asn"] == probe_asn, result


@pytest.mark.parametrize(
    "field", [
        "measurement_start_day",
        "domain",
        "probe_cc",
        "probe_asn",
        "test_name",
        "input",
    ]
)
def test_oonidata_aggregation_analysis_with_axis_x(client, field):
    params = {
        "since": since,
        "until": until,
        "axis_x": field
    }

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[field] is not None, result


@pytest.mark.parametrize(
    "field", [
        "measurement_start_day",
        "domain",
        "probe_cc",
        "probe_asn",
        "test_name",
        "input",
    ]
)
def test_oonidata_aggregation_analysis_axis_y(client, field):
    params = {
        "since": since,
        "until": until,
        "axis_y": field
    }

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
    ]
)
def test_oonidata_aggregation_analysis_time_grain(client, time_grain, total):
    params = {
        "since": since,
        "until": until,
        "time_grain": time_grain
    }

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == total

