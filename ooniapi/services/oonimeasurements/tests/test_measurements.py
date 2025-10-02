import pytest
from datetime import datetime, timezone, timedelta
from clickhouse_driver import Client as Clickhouse
from oonimeasurements.common.clickhouse_utils import query_click_one_row
from oonimeasurements.routers.v1.measurements import format_msmt_meta
import oonimeasurements.routers.v1.measurements as measurements
from sqlalchemy import sql
from .conftest import THIS_DIR

route = "api/v1/measurements"


def fake_get_bucket_url(bucket_name):
    return f"file://{THIS_DIR}/fixtures/"


def normalize_probe_asn(probe_asn):
    if probe_asn.startswith("AS"):
        return probe_asn
    return f"AS{probe_asn}"

def get_time(row):
    return datetime.strptime(row["measurement_start_time"], "%Y-%m-%dT%H:%M:%S.%fZ")

SINCE = datetime.strftime(datetime(2020, 1, 1), "%Y-%m-%dT%H:%M:%S.%fZ")

def test_list_measurements(client):
    response = client.get(route, params={"since":SINCE})
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
    params["since"] = SINCE

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
        "since": SINCE
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
    params['since'] = SINCE
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
    params = {"domain": domainCollection, "since" : SINCE}

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
        "/api/v1/measurements", params={"order_by": "measurement_start_time", "since" : SINCE}
    )
    assert (
        resp.status_code == 200
    ), f"Unexpected status code: {resp.status_code}. {resp.content}"
    j = resp.json()
    assert len(j["results"]) > 1, "Not enough results"


    d = get_time(j["results"][0])
    for row in j["results"][1:]:
        next_d = get_time(row)
        assert next_d <= d, "Results should be in descending order"
        d = next_d


def test_msm_meta_probe_asn_int(client, monkeypatch):
    """
    The monolith returns probe_asn as an int in /measurement_meta
    This test ensures the same functionality
    """
    monkeypatch.setattr(measurements, "get_bucket_url", fake_get_bucket_url)

    report_id = "20250709T074749Z_webconnectivity_US_10796_n1_oljUoi3ZVNHUzjdp"
    input = "https://www.quora.com/"
    resp = client.get(
        "/api/v1/measurement_meta",
        params={"report_id": report_id, "full": True, "input": input},
    )

    assert resp.status_code == 200, resp.content
    j = resp.json()
    assert isinstance(j["probe_asn"], int), "probe_asn should be int"


def test_fix_msm_date_parsing(client):

    # This query was raising an error parsing the date:
    # /api/v1/measurements?probe_cc=SY&since=2025-09-29T00:00:00&until=2025-09-29T23:59:59&limit=2000&since_index=20250910T105502Z_tor_SY_29256_n1_C8NFgxmJpyaP5Bsd
    resp = client.get(
        "/api/v1/measurements",
        params={
            "since": "2025-09-29T00:00:00",
            "until": "2025-09-29T23:59:59",
            "limit": "2000",
        },
    )

    assert resp.status_code == 200, resp.content


def test_get_measurement_meta_basic(client):
    rid = "20210709T004340Z_webconnectivity_MY_4818_n1_YCM7J9mGcEHds2K3"
    inp = "https://www.backtrack-linux.org/"
    response = client.get(f"/api/v1/measurement_meta?report_id={rid}&input={inp}")
    assert response.status_code == 200, response.status_code
    j = response.json()
    assert j == {
        "anomaly": True,
        "confirmed": False,
        "failure": False,
        "input": inp,
        "measurement_start_time": "2025-07-09T00:55:13Z",
        "measurement_uid": "20210709005529.664022_MY_webconnectivity_68e5bea1060d1874",
        "probe_asn": 4818,
        "probe_cc": "MY",
        "report_id": rid,
        "scores": '{"blocking_general":1.0,"blocking_global":0.0,"blocking_country":0.0,"blocking_isp":0.0,"blocking_local":0.0,"analysis":{"blocking_type":"http-failure"}}',
        "test_name": "web_connectivity",
        "test_start_time": "2025-07-09T00:43:40Z",
        "category_code": "",
    }


def test_get_measurement_meta_invalid_rid(client):
    response = client.get("/api/v1/measurement_meta?report_id=BOGUS")
    assert b"Invalid report_id" in response.content


def test_get_measurement_meta_not_found(client):
    url = "/api/v1/measurement_meta?report_id=20200712T100000Z_AS9999_BOGUSsYKWBS2S0hdzXf7rhUusKfYP5cQM9HwAdZRPmUfroVoCn"
    resp = client.get(url)
    # TODO: is this a bug?
    assert resp.status_code == 200
    assert resp.json() == {}


def test_get_measurement_meta_input_none_from_fp(client):
    rid = "20210709T000017Z_httpinvalidrequestline_CH_3303_n1_8mr2M3dzkoFmmjIU"
    # input is None
    response = client.get(f"/api/v1/measurement_meta?report_id={rid}")
    assert response.status_code == 200, response.status_code
    assert response.json() == {
        "anomaly": False,
        "category_code": None,
        "confirmed": False,
        "failure": False,
        "input": "",
        "measurement_start_time": "2021-07-09T00:00:18Z",
        "measurement_uid": "20210709000024.440526_CH_httpinvalidrequestline_3937f817503ed4ea",
        "probe_asn": 3303,
        "probe_cc": "CH",
        "report_id": rid,
        "scores": '{"blocking_general":0.0,"blocking_global":0.0,"blocking_country":0.0,"blocking_isp":0.0,"blocking_local":0.0}',
        "test_name": "http_invalid_request_line",
        "test_start_time": "2021-07-09T00:00:16Z",
    }


def test_get_measurement_meta_full(client, monkeypatch):
    monkeypatch.setattr(measurements, "get_bucket_url", fake_get_bucket_url)

    rid = "20210709T004340Z_webconnectivity_MY_4818_n1_YCM7J9mGcEHds2K3"
    inp = "https://www.backtrack-linux.org/"
    response = client.get(
        f"/api/v1/measurement_meta?report_id={rid}&input={inp}&full=True"
    )
    assert response.status_code == 200, response.status_code
    data = response.json()
    raw_msm = data.pop("raw_measurement")
    assert data == {
        "anomaly": True,
        "confirmed": False,
        "failure": False,
        "input": inp,
        "measurement_uid": "20210709005529.664022_MY_webconnectivity_68e5bea1060d1874",
        "measurement_start_time": "2025-07-09T00:55:13Z",
        "probe_asn": 4818,
        "probe_cc": "MY",
        "scores": '{"blocking_general":1.0,"blocking_global":0.0,"blocking_country":0.0,"blocking_isp":0.0,"blocking_local":0.0,"analysis":{"blocking_type":"http-failure"}}',
        "report_id": rid,
        "test_name": "web_connectivity",
        "test_start_time": "2025-07-09T00:43:40Z",
        "category_code": "",
    }
    assert raw_msm

def test_no_measurements_before_30_days(client):
    """
    The default filtering should not retrieve measurements older than 30 days since tomorrow
    """

    resp = client.get("/api/v1/measurements") # no since/until
    assert resp.status_code, resp.status_code
    json = resp.json()
    min_date = datetime.now(timezone.utc) - timedelta(29)
    for r in json['results']:
        date = get_time(r)
        assert date >= min_date

def test_asn_to_int():
    assert measurements.asn_to_int("AS1234") == 1234
    assert measurements.asn_to_int("1234") == 1234
