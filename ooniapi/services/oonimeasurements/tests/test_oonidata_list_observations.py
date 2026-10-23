import pytest

route = "api/v1/observations"

measurement_uid = "20241101233410.169530_DE_webconnectivity_2eb2a331c9ce0630"


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"since": "2024-11-01", "until": "2024-11-02"},
        {"probe_cc": "DE"},
    ],
)
def test_list_obs_without_report_id_or_measurement_uid_fails(client, params):
    response = client.get(route, params=params)
    assert response.status_code == 400, response.json()


def test_list_obs_measurement_uid_only(client):
    """
    With only measurement_uid, no date window is applied, so rows still match
    even when their measurement_start_time is old.
    """
    by_uid = client.get(route, params={"measurement_uid": measurement_uid})
    assert by_uid.status_code == 200
    j = by_uid.json()
    assert isinstance(j["results"], list), j
    assert len(j["results"]) > 0
    for row in j["results"]:
        assert row["measurement_uid"] == measurement_uid, row


def test_list_obs_report_id_only(client):
    report_id = "20241101T233351Z_webconnectivity_DE_3209_n1_I7QVY7IdnaSfYmsb"

    by_report = client.get(route, params={"report_id": report_id})
    assert by_report.status_code == 200
    j = by_report.json()
    assert isinstance(j["results"], list), j
    assert len(j["results"]) > 0
    for row in j["results"]:
        assert row["report_id"] == report_id, row


def test_list_obs_measurement_uid_with_explicit_since_and_until(client):
    """
    An explicit since/until must still be honored even when measurement_uid is set.
    """
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
    "filter_name, filter_value",
    [
        ("report_id", "20241101T233351Z_webconnectivity_DE_3209_n1_I7QVY7IdnaSfYmsb"),
        ("probe_asn", 3209),
        ("probe_cc", "DE"),
        ("software_name", "ooniprobe-android-unattended"),
        ("software_version", "4.0.0"),
        ("test_name", "web_connectivity"),
        ("test_version", "0.4.3"),
        ("engine_version", "3.23.0"),
    ],
)
def test_oonidata_list_observations_with_filters(client, filter_name, filter_value):
    params = {"measurement_uid": measurement_uid, filter_name: filter_value}

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[filter_name] == filter_value, result


def test_oonidata_list_observations_filtering_by_probe_asn_as_a_string(client):
    params = {"measurement_uid": measurement_uid, "probe_asn": "AS3209"}

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result["probe_asn"] == 3209, result


def test_oonidata_list_observations_with_limit_and_offset(client):
    params = {"measurement_uid": measurement_uid, "limit": 5}

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 5
