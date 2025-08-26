import pytest
from clickhouse_driver import Client as Clickhouse
from oonimeasurements.common.clickhouse_utils import query_click_one_row
from oonimeasurements.routers.v1.measurements import format_msmt_meta
import oonimeasurements.routers.v1.measurements as measurements
from sqlalchemy import sql
from .conftest import get_file_path

route = "api/v1/measurements"


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

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    for result in json["results"]:
        assert result[filter_param] in filter_value, result


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


def test_raw_measurement_args_optional(client, monkeypatch, s3_files):
    """
    Test that all arguments in raw_measurements are optional
    """

    def fake_get_bucket_url(bucket_name):
        return f"file://{s3_files}"

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
