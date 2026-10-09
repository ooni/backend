from datetime import datetime, timedelta

import pytest
from clickhouse_driver import Client as ClickhouseClient

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


ORDER_BY = ["measurement_start_time", "input", "probe_cc", "probe_asn", "test_name"]
PAGING_SINCE, PAGING_UNTIL = "2019-04-30", "2019-05-02"
PAGING_WHERE = f"probe_cc = 'ZY' AND measurement_start_time >= '{PAGING_SINCE}' AND measurement_start_time <= '{PAGING_UNTIL}'"
# observations per measurement, and minutes from 2019-04-30 23:55 to its start
OBSERVATIONS = [3, 1, 5, 2, 4, 3, 1, 2]
MINUTES = [0, 0, 5, 9, 9, 12, 12, 15]
COPIED = [(1, 0), (2, 3), (4, 1)]  # (measurement, observation_idx) stored twice


def paging_uid(m):
    return f"20190430{m:06d}.000000_ZY_webconnectivity_paging"


@pytest.fixture(scope="module", params=[False, True], ids=["once", "copies"])
def paged_observations(db, request):
    """
    Observations shaped like production's: those of one measurement share
    measurement_start_time and some measurements share it too, so every
    order_by has ties; the rows span two monthly partitions and several parts.
    With copies, some observations are stored twice, as ooni/data reprocessing
    leaves them until a merge.
    """
    start = datetime(2019, 4, 30, 23, 55, 0, 123000)
    measurements = []
    for m, (count, minutes) in enumerate(zip(OBSERVATIONS, MINUTES)):
        t = start + timedelta(minutes=minutes)
        measurements.append([
            (
                paging_uid(m),
                idx,
                t,
                t.strftime("%Y-%m-%d"),
                "ZY",
                m % 3,
                "web_connectivity" if m % 2 else "signal",
                None if m == 2 else f"https://paging{m % 3}.example.org/",
                f"ZY_paging_report{m // 3}",
            )
            for idx in range(count)
        ])
    insert = (
        "INSERT INTO obs_web (measurement_uid, observation_idx, measurement_start_time, bucket_date,"
        " probe_cc, probe_asn, test_name, input, report_id) VALUES"
    )
    with ClickhouseClient.from_url(db) as click:
        # a copy in a separate part stays until merged, as ReplacingMergeTree allows
        click.execute("SYSTEM STOP MERGES obs_web")
        try:
            for batch in (measurements[:3], measurements[3:6], measurements[6:]):
                click.execute(insert, [row for rows in batch for row in rows])
            copies = [measurements[m][idx] for m, idx in COPIED] if request.param else []
            if copies:
                click.execute(insert, copies)
            yield click, sum(OBSERVATIONS) + len(copies)
        finally:
            click.execute("SYSTEM START MERGES obs_web")
            click.execute("DELETE FROM obs_web WHERE probe_cc = 'ZY'")


def single_query(click, where, order_by, order, offset, limit):
    """The page as the endpoint's single query returned it, with the tie-breaker."""
    rows = click.execute(
        f"SELECT measurement_uid, observation_idx FROM obs_web WHERE {where}"
        f" ORDER BY {order_by} {order}, measurement_uid, observation_idx LIMIT {limit} OFFSET {offset}"
    )
    return [tuple(r) for r in rows]


def get_page(client, offset, limit, **params):
    params = {"offset": offset, "limit": limit, **params}
    response = client.get(route, params=params)
    assert response.status_code == 200, response.text
    return [(r["measurement_uid"], r["observation_idx"]) for r in response.json()["results"]]


def paging_params(order_by, order):
    return {"probe_cc": "ZY", "since": PAGING_SINCE, "until": PAGING_UNTIL, "order_by": order_by, "order": order}


@pytest.mark.parametrize("order", ["ASC", "DESC"])
@pytest.mark.parametrize("order_by", ORDER_BY)
def test_oonidata_list_observations_pages_match_single_query(client, paged_observations, order_by, order):
    click, count = paged_observations
    for limit in [1, 2, 4, 5, 7]:
        for offset in range(count + 2):
            expected = single_query(click, PAGING_WHERE, order_by, order, offset, limit)
            got = get_page(client, offset, limit, **paging_params(order_by, order))
            assert got == expected, (limit, offset)


@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("order_by", ORDER_BY)
@pytest.mark.parametrize("limit", [1, 4, 5])
def test_oonidata_list_observations_paging_returns_every_row(client, paged_observations, order_by, order, limit):
    click, count = paged_observations
    seen = []
    for offset in range(0, count + limit, limit):
        seen += get_page(client, offset, limit, **paging_params(order_by, order))
    stored = click.execute(f"SELECT measurement_uid, observation_idx FROM obs_web WHERE {PAGING_WHERE}")
    assert sorted(seen) == sorted(tuple(r) for r in stored), "rows missing or repeated"
    assert seen == single_query(click, PAGING_WHERE, order_by, order, 0, count)


@pytest.mark.parametrize(
    "params, where",
    [
        ({"report_id": "ZY_paging_report0"}, "report_id = 'ZY_paging_report0'"),
        ({"measurement_uid": paging_uid(2)}, f"measurement_uid = '{paging_uid(2)}'"),
        (
            {"probe_cc": "ZY", "probe_asn": "AS1", "test_name": "web_connectivity", "since": PAGING_SINCE, "until": PAGING_UNTIL},
            f"{PAGING_WHERE} AND probe_asn = 1 AND test_name = 'web_connectivity'",
        ),
    ],
    ids=["report_id", "measurement_uid", "filters"],
)
@pytest.mark.parametrize("order", ["ASC", "desc"])
def test_oonidata_list_observations_filtered_pages_match_single_query(client, paged_observations, params, where, order):
    click, _ = paged_observations
    count = click.execute(f"SELECT count() FROM obs_web WHERE {where}")[0][0]
    assert count > 1
    for limit in [1, 2, 3]:
        for offset in range(count + 1):
            expected = single_query(click, where, "measurement_start_time", order, offset, limit)
            got = get_page(client, offset, limit, order=order, **params)
            assert got == expected, (limit, offset)


def test_oonidata_list_observations_reads_keys_again_only_for_copies(client, paged_observations, monkeypatch):
    from oonimeasurements.routers.data import list_observations

    click, count = paged_observations
    queries = []

    async def counting(db, q, q_args, *args, **kwargs):
        queries.append(q)
        return await list_observations_query(db, q, q_args, *args, **kwargs)

    list_observations_query = list_observations.async_query_click
    monkeypatch.setattr(list_observations, "async_query_click", counting)
    read_again = 0
    for offset in range(count):
        queries.clear()
        page = get_page(client, offset, 3, **paging_params("measurement_start_time", "ASC"))
        rows = click.execute(
            f"SELECT count() FROM obs_web WHERE {PAGING_WHERE} AND (measurement_uid, observation_idx) IN %(keys)s",
            {"keys": page},
        )[0][0] if page else 0
        assert len(queries) == (2 if rows > len(set(page)) else 1), offset
        read_again += len(queries) == 2
    assert (read_again > 0) == (count > sum(OBSERVATIONS))
