import pytest
from freezegun import freeze_time

route = "api/v1/observations"


def test_oonidata_list_observations(client):
    response = client.get(route)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 0


def test_list_obs_default_window_is_last_complete_hour(client):
    """
    The fixture report has observations from 2024-11-01 23:33 UTC. The hour
    23:00-00:00 becomes the default window once the pipeline has had 90
    minutes to process it, and stays it for an hour.
    """
    report_id = "20241101T233351Z_webconnectivity_DE_3209_n1_I7QVY7IdnaSfYmsb"

    def default_report_ids():
        response = client.get(route, params={"limit": 1000})
        assert response.status_code == 200
        return {r["report_id"] for r in response.json()["results"]}

    with freeze_time("2024-11-02T01:29:59Z"):
        assert report_id not in default_report_ids()
    for now in ("2024-11-02T01:30:00Z", "2024-11-02T02:29:59Z"):
        with freeze_time(now):
            assert report_id in default_report_ids()
    with freeze_time("2024-11-02T02:30:00Z"):
        assert report_id not in default_report_ids()


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"since": "2024-11-01", "until": "2024-11-02"},
        {"report_id": "20241101T233351Z_webconnectivity_DE_3209_n1_I7QVY7IdnaSfYmsb"},
        {"probe_cc": "DE"},
    ],
)
def test_list_obs_without_measurement_uid_is_deprecated(client, params):
    response = client.get(route, params=params)
    assert response.status_code == 200
    assert response.headers["Deprecation"] == "@1792972800"  # 2026-10-26
    assert "measurement_uid" in response.json()["metadata"]["deprecation"]


def test_list_obs_measurement_uid_is_not_deprecated(client):
    measurement_uid = "20241101233410.169530_DE_webconnectivity_2eb2a331c9ce0630"
    response = client.get(route, params={"measurement_uid": measurement_uid})
    assert response.status_code == 200
    assert "Deprecation" not in response.headers
    assert response.json()["metadata"]["deprecation"] is None


def test_list_obs_report_id_only_skips_default_date_window(client):
    """
    Without report_id, since/until default to the last complete hour (fixture data is older).

    With only report_id, those defaults must not apply, so rows still match by report_id
    even when their measurement_start_time falls outside the usual default window.
    """
    report_id = "20241101T233351Z_webconnectivity_DE_3209_n1_I7QVY7IdnaSfYmsb"

    default_response = client.get(route)
    assert default_response.status_code == 200
    assert len(default_response.json()["results"]) == 0

    by_report = client.get(route, params={"report_id": report_id})
    assert by_report.status_code == 200
    j = by_report.json()
    assert isinstance(j["results"], list), j
    assert len(j["results"]) > 0
    for row in j["results"]:
        assert row["report_id"] == report_id, row


def test_list_obs_measurement_uid_only_skips_default_date_window(client):
    """
    Without measurement_uid, since/until default to the last complete hour (fixture data is older).

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
    for row in j["results"]:
        assert row["measurement_uid"] == measurement_uid, row


def test_list_obs_measurement_uid_with_explicit_since_and_until(client):
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


def test_oonidata_list_observations_with_since_and_until(
    client, params_since_and_until_with_two_days
):
    response = client.get(route, params=params_since_and_until_with_two_days)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert "test_name" in result, result
        assert "probe_cc" in result, result


@pytest.mark.parametrize(
    "filter_name, filter_value",
    [
        ("report_id", "20241101T233351Z_webconnectivity_DE_3209_n1_I7QVY7IdnaSfYmsb"),
        (
            "measurement_uid",
            "20241101233410.169530_DE_webconnectivity_2eb2a331c9ce0630",
        ),
        ("probe_asn", 45758),
        ("probe_cc", "IT"),
        ("software_name", "ooniprobe-cli"),
        ("software_version", "3.20.0"),
        ("test_name", "web_connectivity"),
        ("test_version", "0.4.3"),
        ("engine_version", "3.20.0"),
    ],
)
def test_oonidata_list_observations_with_filters(
    client, filter_name, filter_value, params_since_and_until_with_two_days
):
    params = params_since_and_until_with_two_days
    params[filter_name] = filter_value

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[filter_name] == filter_value, result


def test_oonidata_list_observations_filtering_by_probe_asn_as_a_string_with_since_and_until(
    client, params_since_and_until_with_two_days
):
    params = params_since_and_until_with_two_days
    probe_asn = 45758
    params["probe_asn"] = "AS" + str(probe_asn)

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result["probe_asn"] == probe_asn, result


def test_oonidata_list_observations_order_default(
    client, params_since_and_until_with_two_days
):
    response = client.get(route, params=params_since_and_until_with_two_days)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for i in range(1, len(json["results"])):
        assert "measurement_start_time" in json["results"][i], json["results"][i]
        previous_date = json["results"][i - 1]["measurement_start_time"]
        current_date = json["results"][i]["measurement_start_time"]
        assert (
            previous_date >= current_date
        ), f"The dates are not ordered: {previous_date} < {current_date}"


def test_oonidata_list_observations_order_asc(
    client, params_since_and_until_with_two_days
):
    params = params_since_and_until_with_two_days
    params["order"] = "ASC"

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for i in range(1, len(json["results"])):
        assert "measurement_start_time" in json["results"][i], json["results"][i]
        previous_date = json["results"][i - 1]["measurement_start_time"]
        current_date = json["results"][i]["measurement_start_time"]
        assert (
            previous_date <= current_date
        ), f"The dates are not ordered: {previous_date} > {current_date}"


@pytest.mark.parametrize(
    "field, order",
    [
        ("input", "asc"),
        ("probe_cc", "asc"),
        ("probe_asn", "asc"),
        ("test_name", "asc"),
        ("input", "desc"),
        ("probe_cc", "desc"),
        ("probe_asn", "desc"),
        ("test_name", "desc"),
    ],
)
def test_oonidata_list_observations_order_by_field(
    client, field, order, params_since_and_until_with_two_days
):
    params = params_since_and_until_with_two_days
    params["order_by"] = field
    params["order"] = order

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for i in range(1, len(json["results"])):
        assert field in json["results"][i], json["results"][i]
        previous = json["results"][i - 1][field]
        current = json["results"][i][field]
        if order == "asc":
            assert (
                previous <= current
            ), f"The {field} values are not ordered in ascending order: {previous} > {current}"
        else:
            assert (
                previous >= current
            ), f"The {field} values are not ordered in descending order: {previous} < {current}"


def test_oonidata_list_observations_limit_by_default(
    client, params_since_and_until_with_two_days
):
    response = client.get(route, params=params_since_and_until_with_two_days)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 100


def test_oonidata_list_observations_with_limit_and_offset(
    client, params_since_and_until_with_two_days
):
    params = params_since_and_until_with_two_days
    params["limit"] = 10

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 10
