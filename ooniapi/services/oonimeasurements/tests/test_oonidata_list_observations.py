import pytest

route = "api/v1/observations"


def test_oonidata_list_observations(client):
    response = client.get(route)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 0


def test_list_obs_report_id_only_skips_default_date_window(client):
    """
    Without report_id, since/until default to the last 7 days (fixture data is older).

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
    Without measurement_uid, since/until default to the last 7 days (fixture data is older).

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


@pytest.fixture(scope="module")
def paged_observations(db):
    from datetime import datetime, timedelta
    from clickhouse_driver import Client as ClickhouseClient

    start = datetime(2019, 4, 1)
    rows = [
        (f"20190401{i:06d}.000000_ZY_webconnectivity_paging", idx, start + timedelta(minutes=i * 4 + idx), "ZY", f"paging{i}.example.org")
        for i in range(3)
        for idx in range(4)
    ]
    insert = "INSERT INTO obs_web (measurement_uid, observation_idx, measurement_start_time, probe_cc, hostname) VALUES"
    with ClickhouseClient.from_url(db) as click:
        # a duplicate in a separate part stays until merged, as ReplacingMergeTree allows
        click.execute("SYSTEM STOP MERGES obs_web")
        try:
            click.execute(insert, rows)
            click.execute(insert, [rows[5]])
            yield click
        finally:
            click.execute("SYSTEM START MERGES obs_web")


@pytest.mark.parametrize(
    "order, offset, limit",
    [("DESC", 0, 5), ("ASC", 3, 4), ("DESC", 10, 5), ("ASC", 0, 100)],
)
def test_oonidata_list_observations_page_matches_plain_query(client, paged_observations, order, offset, limit):
    params = {"probe_cc": "ZY", "since": "2019-04-01", "until": "2019-04-02", "order": order, "offset": offset, "limit": limit}
    response = client.get(route, params=params)
    assert response.status_code == 200, response.text
    got = [(r["measurement_uid"], r["observation_idx"]) for r in response.json()["results"]]

    expected = paged_observations.execute(
        "SELECT measurement_uid, observation_idx FROM obs_web"
        " WHERE probe_cc = 'ZY' AND measurement_start_time >= '2019-04-01' AND measurement_start_time <= '2019-04-02'"
        f" ORDER BY measurement_start_time {order} LIMIT {limit} OFFSET {offset}"
    )
    assert got == [tuple(r) for r in expected]
    assert len(got) == min(limit, max(13 - offset, 0))
