import pytest

from sqlalchemy import text
from sqlalchemy.sql import sqltypes
from sqlalchemy.sql.elements import Label, ColumnElement
from sqlalchemy.dialects import postgresql

from oonimeasurements.routers.data.aggregate_analysis import format_aggregate_query

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


def test_oonidata_format_aggregate_query():
    extra_cols = {"probe_asn": "probe_asn", "domain": "domain"}
    where = ""
    ## TODO: add more rigorous tests that validate the correct column ordering
    q, fixed_cols = format_aggregate_query(extra_cols, where)
    for col in fixed_cols:
        assert col in q

    q, fixed_cols = format_aggregate_query(extra_cols, where, split_dns_outcome=True)
    for col in fixed_cols:
        assert col in q


def test_oonidata_detector_events(client, params_since_and_until_with_ten_days):
    params = params_since_and_until_with_ten_days

    response = client.get("api/v1/detector/events", params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    print(json["results"])
