import pytest
from datetime import datetime
from clickhouse_driver import Client as Clickhouse
from oonimeasurements.common.clickhouse_utils import query_click_one_row
from oonimeasurements.routers.v1.measurements import format_msmt_meta
import oonimeasurements.routers.v1.measurements as measurements
from sqlalchemy import sql
from .conftest import THIS_DIR

route = "api/v1/measurements"


def normalize_probe_asn(probe_asn):
    if probe_asn.startswith("AS"):
        return probe_asn
    return f"AS{probe_asn}"


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
        ("probe_asn", "30722"),
    ],
)
def test_list_measurements_with_one_value_to_filters(
    client, filter_param, filter_value
):
    params = {}
    params[filter_param] = filter_value

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0

    # we support filtering without the AS prefix, but it's always included in
    # the return value
    if filter_param == "probe_asn":
        filter_value = normalize_probe_asn(filter_value)
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
    ],
)
def test_list_measurements_with_multiple_values_to_filters(
    client, filter_param, filter_value
):
    params = {}
    params[filter_param] = filter_value
    filter_value_list = filter_value.split(",")
    if filter_param == "probe_asn":
        filter_value_list = list(map(normalize_probe_asn, filter_value_list))

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[filter_param] in filter_value_list, result


def test_list_measurements_with_multiple_values_to_filters_not_in_the_result(client):
    domainCollection = "cloudflare-dns.com, adblock.doh.mullvad.net, 1.1.1.1"
    params = {"domain": domainCollection}

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    domain_list = domainCollection.split(", ")
    for result in json["results"]:
        assert any(domain in result["input"] for domain in domain_list), result


def test_failure_format(db):
    ch = Clickhouse.from_url(db)

    msm = (
        query_click_one_row(
            ch,
            "SELECT * FROM fastpath WHERE test_name = 'web_connectivity' LIMIT 1",
            {},
        )
        or {}
    )
    uid = msm["measurement_uid"]

    q = """
    SELECT * FROM fastpath
        LEFT OUTER JOIN citizenlab ON citizenlab.url = fastpath.input
        WHERE measurement_uid = :uid
        LIMIT 1
    """
    query_params = dict(uid=uid)
    row = query_click_one_row(ch, sql.text(q), query_params, query_prio=3) or {}

    # Validation shouldn't crash
    format_msmt_meta(row)


def test_raw_measurement_args_optional(client, monkeypatch, maybe_download_fixtures):
    """
    Test that all arguments in raw_measurements are optional
    """

    def fake_get_bucket_url(bucket_name):
        return f"file://{THIS_DIR}/fixtures/"

    monkeypatch.setattr(measurements, "get_bucket_url", fake_get_bucket_url)

    # Taken from fixtures
    uid = "20250709075147.833477_US_webconnectivity_8f0e0b49950f2592"
    rid = "20250709T074913Z_webconnectivity_US_10796_n1_XDgk16bsGyJbx6Jl"

    resp = client.get("/api/v1/raw_measurement", params={"measurement_uid": uid})
    assert resp.status_code == 200, resp.status_code

    resp = client.get(
        "/api/v1/raw_measurement",
        params={"report_id": rid, "input": "https://freenetproject.org/"},
    )
    assert resp.status_code == 200, resp.status_code

    resp = client.get("/api/v1/raw_measurement", params={})
    assert resp.status_code == 400, resp.status_code


def test_raw_measurement_returns_json(client, monkeypatch, maybe_download_fixtures):
    """
    Test that raw_measurements returns json instead of a string
    """

    def fake_get_bucket_url(bucket_name):
        return f"file://{THIS_DIR}/fixtures/"

    monkeypatch.setattr(measurements, "get_bucket_url", fake_get_bucket_url)

    uid = "20250709075147.833477_US_webconnectivity_8f0e0b49950f2592"
    resp = client.get("/api/v1/raw_measurement", params={"measurement_uid": uid})
    assert resp.status_code == 200, resp.status_code

    j = resp.json()
    assert isinstance(j, dict), type(j)

    # When not found should return empty dict
    uid = "20250709075147.833477_US_webconnectivity_baddbaddbaddbadd"
    resp = client.get("/api/v1/raw_measurement", params={"measurement_uid": uid})
    assert resp.status_code == 200, resp.status_code

    j = resp.json()
    assert j == {}, j


def test_measurements_order_by_test_start_time_forbidden(client):
    """
    Tests that the `test_start_time` is NOT a valid order by field in oonimeasurements
    """

    resp = client.get("/api/v1/measurements", params={"order_by": "test_start_time"})

    assert resp.status_code != 200, f"Unexpected code: {resp.status_code}"


def test_measurements_limit_hard_capped(client):
    """
    Tests that the `limit` field in oonimeasurements is hard capped to 1_000_000
    """

    valids = [50, 1_000_000]
    for valid in valids:
        resp = client.get("/api/v1/measurements", params={"limit": valid})
        assert resp.status_code == 200, f"Unexpected code: {resp.status_code}"

    resp = client.get("/api/v1/measurements", params={"limit": 1_000_001})
    assert resp.status_code != 200, f"Unexpected code: {resp.status_code}"


def test_measurements_desc_default(client):
    """
    Test that the default ordering is descending by default
    """

    resp = client.get(
        "/api/v1/measurements", params={"order_by": "measurement_start_time"}
    )
    assert (
        resp.status_code == 200
    ), f"Unexpected status code: {resp.status_code}. {resp.content}"
    j = resp.json()
    assert len(j["results"]) > 1, "Not enough results"

    def get_time(row):
        return datetime.strptime(row["measurement_start_time"], "%Y-%m-%dT%H:%M:%S.%fZ")

    d = get_time(j["results"][0])
    for row in j["results"][1:]:
        next_d = get_time(row)
        assert next_d <= d, "Results should be in descending order"
        d = next_d

def test_fix_msm_date_parsing(client):

    # This query was raising an error parsing the date:
    # /api/v1/measurements?probe_cc=SY&since=2025-09-29T00:00:00&until=2025-09-29T23:59:59&limit=2000&since_index=20250910T105502Z_tor_SY_29256_n1_C8NFgxmJpyaP5Bsd
    resp = client.get("/api/v1/measurements", params={
        "since" : "2025-09-29T00:00:00",
        "until" : "2025-09-29T23:59:59",
        "limit" : "2000"
    })

    assert resp.status_code == 200, resp.content