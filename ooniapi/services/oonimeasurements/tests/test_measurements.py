import pytest
from datetime import datetime, timezone, timedelta
from freezegun import freeze_time
from clickhouse_driver import Client as Clickhouse
from oonimeasurements.common.anonymous_credentials import VerificationStatus
from oonimeasurements.common.clickhouse_utils import query_click_one_row
from oonimeasurements.routers.v1.measurements import format_msmt_meta
import oonimeasurements.routers.v1.measurements as measurements
from sqlalchemy import sql
from urllib.parse import urlparse, parse_qs
from .conftest import THIS_DIR
from .utils import getj, make_fastpath_row

route = "api/v1/measurements"


def fake_get_bucket_url(bucket_name):
    return f"file://{THIS_DIR}/fixtures/"


def normalize_probe_asn(probe_asn):
    if probe_asn.startswith("AS"):
        return probe_asn
    return f"AS{probe_asn}"


def get_time(row):
    return datetime.strptime(
        row["measurement_start_time"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)


# Use a fixed date from fixtures. Tests will freeze time to make this valid
# Freeze time to 2020-08-01 so that 2020-01-01 is within 6 months (actually 7 months, but close enough)
SINCE = datetime.strftime(datetime(2020, 1, 1), "%Y-%m-%dT%H:%M:%S.%fZ")
# Freeze datetime to this date in tests that use SINCE
FROZEN_TIME = "2025-07-09T00:00:00Z"


@freeze_time("2024-01-30T00:00:00Z")
def test_list_measurements(client):
    response = client.get(route)
    assert response.status_code == 200

    json = response.json()

    assert isinstance(json["results"], list), json
    assert len(json["results"]) == 100



@freeze_time("2024-01-30T00:00:00Z")
def test_list_measurements_verification_status(client, db):
    """List API verification_status must match fastpath.is_verified codes."""
    ch = Clickhouse.from_url(db)
    response = client.get(route, params={"limit": 50})
    assert response.status_code == 200

    results = response.json()["results"]
    assert results

    for result in results:
        uid = result["measurement_uid"]
        assert "verification_status" in result
        row = query_click_one_row(
            ch,
            sql.text(
                "SELECT is_verified FROM fastpath "
                "WHERE measurement_uid = :uid LIMIT 1"
            ),
            {"uid": uid},
        )
        assert row, f"no fastpath row for {uid}"
        is_verified = row["is_verified"]
        expected = VerificationStatus.from_code(is_verified).value
        assert result["verification_status"] == expected, (
            f"{uid}: is_verified={is_verified} expected {expected}, "
            f"got {result['verification_status']}"
        )

@freeze_time("2024-03-01T00:00:00Z")
def test_list_measurements_with_since_and_until(client):
    params = {
        "since": "2024-01-01",
        "until": "2024-01-02",
    }

    response = client.get(route, params=params)
    assert response.status_code == 200
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
@freeze_time("2024-02-01T00:00:00Z")
def test_list_measurements_with_one_value_to_filters(
    client, filter_param, filter_value
):
    params = {}
    params[filter_param] = filter_value
    params["since"] = datetime.now(timezone.utc) - timedelta(days=30 * 5.5)

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


@freeze_time("2024-02-01T00:00:00Z")
def test_list_measurements_with_one_value_to_filters_not_present_in_the_result(client):
    domain = "cloudflare-dns.com"
    params = {"domain": domain, "since": datetime.now(timezone.utc) - timedelta(days=30 * 5.5)}

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
@freeze_time("2024-02-01T00:00:00Z")
def test_list_measurements_with_multiple_values_to_filters(
    client, filter_param, filter_value
):
    params = {
        "since": datetime.now(timezone.utc) - timedelta(days=30 * 5.5)
    }

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


@freeze_time("2024-02-01T00:00:00Z")
def test_list_measurements_with_multiple_values_to_filters_not_in_the_result(client, clickhouse_server):
    domainCollection = "cloudflare-dns.com, adblock.doh.mullvad.net, 1.1.1.1"
    params = {
        "domain": domainCollection,
        "since" : datetime.now(timezone.utc) - timedelta(days=30 * 5.5)
    }

    response = client.get(route, params=params)

    json = response.json()
    assert isinstance(json["results"], list), json
    assert len(json["results"]) > 0
    domain_list = domainCollection.split(", ")

    for result in json["results"]:
        assert any(domain in result["input"] for domain in domain_list), result

    # Make sure all domains show up
    for domain in map(str.strip, domainCollection.split(',')):
        assert any(domain in r['input'] for r in json['results'])


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


@freeze_time(FROZEN_TIME)
def test_measurements_order_by_invalid_value_422(client):
    """
    Tests that invalid `order_by` values return 422 status code,
    and valid `order_by` values return 200 status code
    """
    invalid_values = ["probe_cc", "probe_asn", "test_start_time", "nonexistent"]

    for invalid_value in invalid_values:
        resp = client.get("/api/v1/measurements", params={"order_by": invalid_value})
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}. Response: {resp.json()}"

    valid_values = ["measurement_start_time"]

    for valid_value in valid_values:
        resp = client.get("/api/v1/measurements", params={"order_by": valid_value})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}. Response: {resp.json()}"


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


@freeze_time(FROZEN_TIME)
def test_measurements_desc_default(client):
    """
    Test that the default ordering is descending by default
    """

    resp = client.get(
        "/api/v1/measurements",
        params={"order_by": "measurement_start_time"},
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


def test_no_report_id_msm_uid_400(client):
    """
    measurement_meta should return 400 if neither report_id nor measurement_uid are provided
    """
    resp = client.get("/api/v1/measurement_meta")
    assert resp.status_code == 400


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
        "verification_status" : "unverified"
    }

    # You can also query by measurment uid
    uid = "20210709005529.664022_MY_webconnectivity_68e5bea1060d1874"
    response = client.get("/api/v1/measurement_meta", params={"measurement_uid": uid})
    assert response.status_code == 200, response.status_code


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
        "verification_status" : "unverified"
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
        "verification_status" : "unverified"
    }
    assert raw_msm


def test_bad_report_id_wont_validate(client):

    resp = client.get(
        "/api/v1/measurement_meta",
        params={
            "report_id": "20210709T004340Z_webconnectivity_MY_4818_n1_YCM7J9mGcEHds#$%"  # bad suffix
        },
    )
    assert resp.status_code == 422, resp.json()


@freeze_time(FROZEN_TIME)
def test_no_measurements_before_30_days(client):
    """
    The default filtering should not retrieve measurements older than 30 days since tomorrow
    """

    resp = client.get("/api/v1/measurements")  # no since/until
    assert resp.status_code, resp.status_code
    json = resp.json()
    min_date = datetime.now(timezone.utc) - timedelta(29)
    for r in json["results"]:
        date = get_time(r)
        assert date >= min_date


def test_asn_to_int():
    assert measurements.asn_to_int("AS1234") == 1234
    assert measurements.asn_to_int("1234") == 1234


def test_measurements_date_range_6_months_limit(client):
    """
    Tests that the /measurements endpoint enforces a 6-month date range limit.
    """
    # Range exceeding 6 months should return 400
    resp = client.get("/api/v1/measurements", params={"since": "2024-01-01", "until": "2024-07-20"})
    assert resp.status_code == 400, f"Unexpected status code: {resp.status_code}. Response: {resp.json()}"
    error_detail = resp.json()["detail"]
    assert "time range must not exceed" in error_detail.lower(), f"Unexpected error message: {error_detail}"

    # Range within 6 months should return 200
    resp = client.get("/api/v1/measurements", params={"since": "2024-01-01", "until": "2024-04-01"})
    assert resp.status_code == 200, f"Unexpected status code: {resp.status_code}. Response: {resp.json()}"


def test_list_measurements_pagination_no_duplicates(client, insert_fastpath):
    """
    Inserting a new measurement between page requests should not cause
    measurements to be repeated in the next page.
    """
    test_name = "pagination_test"
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)

    # 1. Add 20 measurements
    rows = [
        make_fastpath_row(test_name, f"{i:04d}", now - timedelta(minutes=i + 1))
        for i in range(20)
    ]
    insert_fastpath(rows)

    # 2. Request first page
    j = getj(client, route, params={"test_name": test_name, "limit": 10})
    first_page = [r["measurement_uid"] for r in j["results"]]
    assert len(first_page) == 10
    next_url = j["metadata"]["next_url"]
    assert next_url is not None
    assert 'cont' in next_url, 'Continuation token should be default option'

    # 3. Add a new measurement
    insert_fastpath([make_fastpath_row(test_name, "0020", now)])

    # 4. Request next page using next_url
    parsed = urlparse(next_url)
    j = getj(client, f"{parsed.path}?{parsed.query}")
    second_page = [r["measurement_uid"] for r in j["results"]]

    all_uids = first_page + second_page
    assert len(all_uids) == len(set(all_uids)), "Duplicated measurements across pages"


def test_list_measurements_offset_wins_over_cont(client, insert_fastpath):
    """
    When both offset and cont are provided, offset-based pagination is used
    and cont is ignored, to avoid breaking legacy clients.
    """
    test_name = "pagination_test"
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    insert_fastpath([
        make_fastpath_row(test_name, f"{i:04d}", now - timedelta(minutes=i + 1))
        for i in range(20)
    ])

    params = {"test_name": test_name, "limit": 10}

    # Get a valid cont token from the first page
    next_url = getj(client, route, params=params)["metadata"]["next_url"]
    cont = parse_qs(urlparse(next_url).query)["cont"][0]

    # Expected result using only offset
    j = getj(client, route, params={**params, "offset": 5})
    expected = [r["measurement_uid"] for r in j["results"]]
    assert len(expected) == 10

    # Using both offset and cont should give the same result as offset only
    j = getj(client, route, params={**params, "offset": 5, "cont": cont})
    got = [r["measurement_uid"] for r in j["results"]]
    assert got == expected

    # next_url should keep using offset
    next_qs = parse_qs(urlparse(j["metadata"]["next_url"]).query)
    assert next_qs["offset"] == ["15"]
    assert "cont" not in next_qs


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_list_measurements_pagination_ordering(client, insert_fastpath, order):
    """
    Paginating with cont should return all measurements exactly once, sorted
    by (measurement_start_time, measurement_uid), including ties on
    measurement_start_time across page boundaries.
    """
    test_name = "pagination_test"
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)

    # 4 timestamps with 3 measurements each, so pages of 2 split tie groups.
    # uid suffixes are not in insertion order so the uid tiebreaker matters
    rows = [
        make_fastpath_row(test_name, f"{t}_{suffix}", now - timedelta(minutes=t + 1))
        for t in range(4)
        for suffix in ["c3", "a1", "b2"]
    ]
    insert_fastpath(rows)

    expected = [
        r["measurement_uid"]
        for r in sorted(
            rows,
            key=lambda r: (r["measurement_start_time"], r["measurement_uid"]),
            reverse=order == "desc",
        )
    ]

    got = []
    j = getj(client, route, params={"test_name": test_name, "limit": 2, "order": order})
    got += [r["measurement_uid"] for r in j["results"]]
    while j["metadata"]["next_url"] is not None:
        assert len(got) <= len(rows), "Pagination is not terminating"
        parsed = urlparse(j["metadata"]["next_url"])
        j = getj(client, f"{parsed.path}?{parsed.query}")
        got += [r["measurement_uid"] for r in j["results"]]

    assert got == expected


def test_list_measurements_limit_zero(client):
    """
    limit=0 is a valid value, it should return no results and no next_url
    """
    j = getj(client, route, params={"limit": 0})
    assert j["results"] == []
    assert j["metadata"]["next_url"] is None


@pytest.mark.parametrize(
    "cont",
    [
        "",
        "nodash",
        "notadate-20260101000000.000000_XY_webconnectivity_0000",
        "2026-01-01-20260101000000.000000_XY_webconnectivity_0000",
        "20260101000000-20260101000000.000000_XY_webconnectivity_0000-extra",
    ],
)
def test_list_measurements_invalid_cont(client, cont):
    resp = client.get(route, params={"cont": cont})
    assert resp.status_code == 400, resp.json()


def test_cont_token_roundtrip():
    msm = measurements.Measurement(
        measurement_url="",
        measurement_start_time=datetime(2026, 9, 24, 10, 37, 49),
        measurement_uid="20260924103750.562725_VE_webconnectivity_239aa1cf9dda27a7",
    )
    start_time, uid = measurements._parse_cont(measurements._make_cont(msm))
    assert start_time == msm.measurement_start_time
    assert uid == msm.measurement_uid



@pytest.mark.parametrize(
    "n_rows, limit, expected_pages",
    [
        # Exact multiple of limit: the last full page still has a next_url,
        # following it returns an empty page
        (10, 5, [5, 5, 0]),
        # Less rows than limit: no next_url
        (3, 5, [3]),
    ],
)
def test_list_measurements_pagination_end(client, insert_fastpath, n_rows, limit, expected_pages):
    test_name = "pagination_test"
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    insert_fastpath([
        make_fastpath_row(test_name, f"{i:04d}", now - timedelta(minutes=i + 1))
        for i in range(n_rows)
    ])

    pages = []
    j = getj(client, route, params={"test_name": test_name, "limit": limit})
    pages.append(len(j["results"]))
    while j["metadata"]["next_url"] is not None:
        assert len(pages) <= len(expected_pages), "Pagination is not terminating"
        parsed = urlparse(j["metadata"]["next_url"])
        j = getj(client, f"{parsed.path}?{parsed.query}")
        pages.append(len(j["results"]))

    assert pages == expected_pages


def test_list_measurements_pagination_late_arrivals(client, insert_fastpath):
    """
    This test documents a limitation of cursor based pagination:

    Measurements inserted after a page was read are only returned if they sort
    after the cursor

    Measurements that sort before the cursor are never returned.
    """
    test_name = "pagination_test"
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)

    rows = [
        make_fastpath_row(test_name, f"{i:04d}", now - timedelta(minutes=i + 1))
        for i in range(20)
    ]
    insert_fastpath(rows)

    # First page (desc): the 10 newest measurements, the cursor points to
    # the measurement started 10 minutes ago
    j = getj(client, route, params={"test_name": test_name, "limit": 10})
    got = [r["measurement_uid"] for r in j["results"]]
    assert got == [r["measurement_uid"] for r in rows[:10]]

    # Late arrivals: received now, but started in the past.
    # - behind: sorts before the cursor, within the already-read page
    # - ahead: sorts after the cursor, within the pages not read yet
    behind = make_fastpath_row(test_name, "behind", now - timedelta(minutes=5, seconds=30), now)
    ahead = make_fastpath_row(test_name, "ahead", now - timedelta(minutes=15, seconds=30), now)
    insert_fastpath([behind, ahead])

    while j["metadata"]["next_url"] is not None:
        assert len(got) <= len(rows) + 2, "Pagination is not terminating"
        parsed = urlparse(j["metadata"]["next_url"])
        j = getj(client, f"{parsed.path}?{parsed.query}")
        got += [r["measurement_uid"] for r in j["results"]]

    assert len(got) == len(set(got)), "Duplicated measurements across pages"
    assert ahead["measurement_uid"] in got
    assert behind["measurement_uid"] not in got
    assert set(r["measurement_uid"] for r in rows) <= set(got)
