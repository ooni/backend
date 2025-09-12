import pytest

from textwrap import dedent
from urllib.parse import urlencode
import json
import pydantic


def is_json(resp):
    return resp.headers.get("content-type") == "application/json"


def fjd(o):
    # non-indented JSON dump
    return json.dumps(o, sort_keys=True)


def api(client, subpath, **kw):
    url = f"/api/v1/{subpath}"
    if kw:
        assert "?" not in url
        url += "?" + urlencode(kw)

    response = client.get(url)
    assert response.status_code == 200, response.text
    assert is_json(response)
    return response.json()


EXPECTED_RESULT_KEYS = [
    "anomaly_count",
    "confirmed_count",
    "failure_count",
    "measurement_count",
    "ok_count",
]


def test_aggregation_no_axis_with_caching(client):
    # 0-dimensional data
    url = "aggregation?probe_cc=IT&probe_asn=AS3269&since=2024-01-01&until=2024-02-01"
    resp = client.get(f"/api/v1/{url}")
    assert resp.status_code == 200, resp
    j = resp.json()
    assert j["dimension_count"] == 0
    assert j["v"] == 0
    assert set(j["result"].keys()) == set(EXPECTED_RESULT_KEYS)

    assert j["result"]["measurement_count"] > 0
    assert j["result"]["ok_count"] > 0

    h = dict(resp.headers)
    # FIXME: caching is currently disabled
    # assert h["Cache-Control"] == "max-age=86400"


def test_aggregation_no_axis_csv(client):
    # 0-dimensional data
    url = "aggregation?probe_cc=IT&probe_asn=AS3269&since=2024-01-01&until=2024-02-01&format=CSV"
    r = client.get(f"/api/v1/{url}")
    assert not is_json(r)
    assert (
        r.text.split("\r")[0]
        == "anomaly_count,confirmed_count,failure_count,measurement_count,ok_count"
    )
    assert "text/csv" in r.headers.get("content-type")
    assert "Content-Disposition" not in r.headers  # not a download


def test_aggregation_no_axis_csv_dload(client):
    # 0-dimensional data
    url = "aggregation?probe_cc=IT&probe_asn=AS3269&since=2024-01-01&until=2024-02-01&format=CSV&download=true"
    r = client.get(f"/api/v1/{url}")
    assert not is_json(r)
    assert "text/csv" in r.headers.get("content-type")
    exp = "attachment; filename=ooni-aggregate-data.csv"
    assert r.headers["Content-Disposition"] == exp


def test_aggregation_no_axis_domain(client):
    # 0-dimensional data
    url = "aggregation?probe_cc=DE&domain=de.rt.com&since=2024-01-01&until=2024-02-01"
    r = client.get(f"/api/v1/{url}")
    j = r.json()
    assert j["dimension_count"] == 0
    assert j["v"] == 0
    assert set(j["result"].keys()) == set(EXPECTED_RESULT_KEYS)

    assert j["result"]["measurement_count"] > 0


def test_aggregation_no_axis_domain_ipaddr(client):
    # 0-dimensional data
    url = "aggregation?domain=8.8.8.8&since=2024-01-01&until=2024-02-01"
    r = client.get(f"/api/v1/{url}")
    j = r.json()
    assert j["dimension_count"] == 0
    assert j["v"] == 0
    assert set(j["result"].keys()) == set(EXPECTED_RESULT_KEYS)

    assert j["result"]["measurement_count"] > 0


def test_aggregation_no_axis_filter_by_category_code(client):
    # 0-dimensional data
    url = "aggregation?probe_cc=IT&since=2024-01-01&until=2024-02-01"
    r = client.get(f"/api/v1/{url}")
    j_nofilter = r.json()

    url = "aggregation?probe_cc=IT&category_code=REL&since=2024-01-01&until=2024-02-01"
    r = client.get(f"/api/v1/{url}")
    j = r.json()
    assert j["dimension_count"] == 0
    assert j["v"] == 0
    assert set(j["result"].keys()) == set(EXPECTED_RESULT_KEYS)

    assert j["result"]["measurement_count"] > 0
    assert j["result"]["ok_count"] > 0
    assert j_nofilter["result"]["measurement_count"] > j["result"]["measurement_count"]


@pytest.mark.skip(reason="TODO: fix this test")
def test_aggregation_no_axis_input_ipaddr(client):
    # 0-dimensional data
    url = "aggregation?input=109.105.109.146:22&since=2021-07-08&until=2021-07-10"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 2,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 2,
            "ok_count": 0,
        },
        "v": 0,
    }, fjd(r)


def test_aggregation_no_axis_filter_multi_domain(client):
    # 0-dimensional data
    url = (
        "aggregation?domain=twitter.com,facebook.com&since=2021-07-09&until=2021-07-10"
    )
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 0,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 24,
            "ok_count": 24,
        },
        "v": 0,
    }, fjd(r)


def test_aggregation_no_axis_filter_multi_probe_asn(client):
    # 0-dimensional dat
    url = "aggregation?probe_asn=AS3303,AS8167&since=2021-07-09&until=2021-07-10"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 10,
            "confirmed_count": 0,
            "failure_count": 4,
            "measurement_count": 24,
            "ok_count": 10,
        },
        "v": 0,
    }, fjd(r)


def test_aggregation_no_axis_filter_multi_probe_cc(client):
    # 0-dimensional data
    url = "aggregation?probe_cc=BR,GB&since=2021-07-09&until=2021-07-10"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 1,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 20,
            "ok_count": 19,
        },
        "v": 0,
    }, fjd(r)


def test_aggregation_no_axis_filter_multi_test_name(client):
    # 0-dimensional data
    url = "aggregation?test_name=web_connectivity,whatsapp&since=2021-07-09&until=2021-07-10"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 11,
            "confirmed_count": 0,
            "failure_count": 2,
            "measurement_count": 57,
            "ok_count": 44,
        },
        "v": 0,
    }, fjd(r)


def test_aggregation_no_axis_filter_multi_test_name_1_axis(client):
    # 1-dimensional: test_name
    url = "aggregation?test_name=web_connectivity,whatsapp&since=2021-07-09&until=2021-07-10&axis_x=test_name"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 1,
        "result": [
            {
                "anomaly_count": 11,
                "confirmed_count": 0,
                "failure_count": 2,
                "measurement_count": 55,
                "ok_count": 42,
                "test_name": "web_connectivity",
            },
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 2,
                "ok_count": 2,
                "test_name": "whatsapp",
            },
        ],
        "v": 0,
    }, fjd(r)


def test_aggregation_no_axis_filter_multi_oonirun(client):
    # 0-dimensional data
    url = "aggregation?ooni_run_link_id=1234,2345&since=2021-07-09&until=2021-07-10"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 0,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 0,
            "ok_count": 0,
        },
        "v": 0,
    }, fjd(r)


def test_aggregation_x_axis_only(client):
    # 1 dimension: X
    url = "aggregation?probe_cc=CH&probe_asn=AS3303&since=2021-07-09&until=2021-07-11&time_grain=day&axis_x=measurement_start_day"
    r = api(client, url)
    r.pop("db_stats", None)
    expected = {
        "dimension_count": 1,
        "result": [
            {
                "anomaly_count": 10,
                "confirmed_count": 0,
                "failure_count": 4,
                "measurement_count": 24,
                "measurement_start_day": "2021-07-09",
                "ok_count": 10,
            },
        ],
        "v": 0,
    }
    assert r == expected, fjd(r)


def test_aggregation_x_axis_only_invalid_range(client):
    # 1 dimension: X
    url = "aggregation?since=2022-07-09&until=2021-07-11&time_grain=day&axis_x=measurement_start_day"
    r = client.get(f"/api/v1/{url}")
    assert r.status_code == 400


def test_aggregation_x_axis_only_invalid_time_grain_too_small(client):
    # 1 dimension: X
    url = "aggregation?since=2020-07-09&until=2022-07-11&time_grain=hour&axis_x=measurement_start_day"
    r = client.get(f"/api/v1/{url}")
    assert r.status_code == 400
    exp = "Choose time_grain between day, week, month, year, auto for the given time range"
    assert r.json()["msg"] == exp


def test_aggregation_x_axis_only_invalid_time_grain_too_large(client):
    # 1 dimension: X
    url = "aggregation?since=2022-07-09&until=2022-07-11&time_grain=year&axis_x=measurement_start_day"
    r = client.get(f"/api/v1/{url}")
    assert r.status_code == 400
    exp = "Choose time_grain between hour, day, auto for the given time range"
    assert r.json()["msg"] == exp


def test_aggregation_x_axis_only_hour(client):
    # 1 dimension: X
    url = "aggregation?since=2021-07-09&until=2021-07-11&axis_x=measurement_start_day"
    r = api(client, url)
    r.pop("db_stats", None)
    expected = {
        "dimension_count": 1,
        "result": [
            {
                "anomaly_count": 9,
                "confirmed_count": 0,
                "failure_count": 2,
                "measurement_count": 20,
                "measurement_start_day": "2021-07-09T00:00:00Z",
                "ok_count": 9,
            },
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 4,
                "measurement_start_day": "2021-07-09T02:00:00Z",
                "ok_count": 4,
            },
        ],
        "v": 0,
    }
    assert r["dimension_count"] == 1
    assert r["result"][:2] == expected["result"], fjd(r)


def test_aggregation_x_axis_domain(client):
    # 1 dimension: X
    url = "aggregation?probe_cc=CH&probe_asn=AS3303&since=2021-07-09&until=2021-07-10&axis_x=domain"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r["dimension_count"] == 1
    for x in r["result"]:
        if x["domain"] == "4genderjustice.org":
            assert x == {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "domain": "4genderjustice.org",
                "failure_count": 0,
                "measurement_count": 1,
                "ok_count": 1,
            }
            return

    assert False, "Msmt not found"


def test_aggregation_x_axis_without_since(client):
    # 1 dimension: X
    url = "aggregation?probe_cc=CH&probe_asn=AS3303&until=2021-07-10&axis_x=measurement_start_day"
    r = client.get(f"/api/v1/{url}")
    assert r.status_code == 400


def test_aggregation_y_axis_only_blocking_type(client):
    # 1 dimension: Y: blocking_type
    url = "aggregation?since=2021-07-09&until=2021-07-10&axis_y=blocking_type"
    r = api(client, url)
    r.pop("db_stats", None)
    expected = {
        "dimension_count": 1,
        "result": [
            {
                "anomaly_count": 2,
                "blocking_type": "",
                "confirmed_count": 0,
                "failure_count": 4,
                "measurement_count": 59,
                "ok_count": 53,
            },
            {
                "anomaly_count": 3,
                "blocking_type": "dns",
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 3,
                "ok_count": 0,
            },
            {
                "anomaly_count": 6,
                "blocking_type": "http-diff",
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 6,
                "ok_count": 0,
            },
            {
                "anomaly_count": 1,
                "blocking_type": "http-failure",
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 1,
                "ok_count": 0,
            },
            {
                "anomaly_count": 1,
                "blocking_type": "tcp_ip",
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 1,
                "ok_count": 0,
            },
        ],
        "v": 0,
    }
    assert r == expected, fjd(r)


def test_aggregation_x_axis_only_probe_cc(client):
    # 1 dimension: X
    url = "aggregation?since=2021-07-09&until=2021-07-10&axis_x=probe_cc"
    r = api(client, url)
    assert r["dimension_count"] == 1
    assert len(r["result"]) == 4


def test_aggregation_x_axis_only_category_code(client):
    # 1-dimensional data
    url = "aggregation?probe_cc=IT&category_code=GRP&since=2021-07-09&until=2021-07-10&axis_x=measurement_start_day"
    r = api(client, url)
    r.pop("db_stats", None)
    expected = {
        "dimension_count": 1,
        "result": [
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "ok_count": 2,
                "measurement_count": 2,
                "measurement_start_day": "2021-07-09T02:00:00Z",
            },
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "ok_count": 1,
                "measurement_count": 1,
                "measurement_start_day": "2021-07-09T03:00:00Z",
            },
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "ok_count": 2,
                "measurement_count": 2,
                "measurement_start_day": "2021-07-09T12:00:00Z",
            },
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "ok_count": 1,
                "measurement_count": 1,
                "measurement_start_day": "2021-07-09T14:00:00Z",
            },
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "ok_count": 1,
                "measurement_count": 1,
                "measurement_start_day": "2021-07-09T17:00:00Z",
            },
        ],
        "v": 0,
    }
    assert r == expected, fjd(r)


def test_aggregation_x_axis_only_csv(client):
    # 1-dimensional data
    url = "aggregation?probe_cc=IT&probe_asn=AS30722&since=2021-07-09&until=2021-07-10&format=CSV&axis_x=measurement_start_day"
    r = client.get(f"/api/v1/{url}")
    assert r.status_code == 200
    assert not is_json(r)
    expected = dedent(
        """\
        anomaly_count,confirmed_count,failure_count,measurement_count,measurement_start_day,ok_count
        0,0,0,4,2021-07-09T02:00:00Z,4
        0,0,0,1,2021-07-09T03:00:00Z,1
        0,0,0,1,2021-07-09T04:00:00Z,1
        0,0,0,1,2021-07-09T07:00:00Z,1
        0,0,0,3,2021-07-09T09:00:00Z,3
        0,0,0,1,2021-07-09T10:00:00Z,1
        0,0,0,1,2021-07-09T12:00:00Z,1
        0,0,0,1,2021-07-09T19:00:00Z,1
    """
    )
    assert r.text.replace("\r", "") == expected


def test_aggregation_x_axis_y_axis(client):
    # 2-dimensional data
    url = "aggregation?since=2021-07-09&until=2021-07-10&axis_x=measurement_start_day&axis_y=probe_cc&test_name=web_connectivity"
    r = api(client, url)

    assert "error" not in r
    assert r["dimension_count"] == 2
    assert len(r["result"]) == 15


def test_aggregation_x_axis_y_axis_are_the_same(client):
    # 2-dimensional data
    url = "aggregation?since=2021-07-09&until=2021-07-10&axis_x=probe_cc&axis_y=probe_cc&test_name=web_connectivity"
    r = client.get(f"/api/v1/{url}")
    assert r.json() == {"msg": "Axis X and Y cannot be the same", "v": 0}


@pytest.mark.skip(reason="TODO: is it correct to skip this behaviour?")
def test_aggregation_two_axis_too_big(client):
    url = "aggregation?since=2008-10-14&until=2021-10-15&test_name=web_connectivity&axis_x=measurement_start_day&axis_y=input"
    r = client.get(f"/api/v1/{url}")
    assert r.json() == {}


def test_aggregation_foo(client):
    url = "aggregation?test_name=web_connectivity&since=2021-07-09&axis_x=probe_cc&until=2021-07-10"
    r = api(client, url)
    assert sorted(r["result"][0]) == [
        "anomaly_count",
        "confirmed_count",
        "failure_count",
        "measurement_count",
        "ok_count",
        "probe_cc",
    ]


def test_aggregation_x_axis_only_csv_2d(client):
    # 2-dimensional data: day vs ASN
    dom = "twitter.com"
    url = f"aggregation?probe_cc=IT&domain={dom}&since=2021-07-09&until=2021-07-10&time_grain=day&axis_x=measurement_start_day&axis_y=probe_asn&format=CSV"
    r = client.get(f"/api/v1/{url}")
    assert r.status_code == 200
    assert not is_json(r)
    expected = dedent(
        """\
    anomaly_count,confirmed_count,failure_count,measurement_count,measurement_start_day,ok_count,probe_asn
    0,0,0,3,2021-07-09,3,3269
    0,0,0,8,2021-07-09,8,12874
    0,0,0,13,2021-07-09,13,30722
    """
    )
    assert r.text.replace("\r", "") == expected


aggreg_over_category_code_expected = [
    {
        "anomaly_count": 0,
        "category_code": "GRP",
        "confirmed_count": 0,
        "failure_count": 0,
        "measurement_count": 7,
        "ok_count": 7,
    },
]


def test_aggregation_x_axis_category_code(client):
    # 1d data over a special column: category_code
    url = (
        "aggregation?probe_cc=IT&since=2021-07-09&until=2021-07-10&axis_x=category_code"
    )
    r = api(client, url)
    assert r["dimension_count"] == 1, fjd(r)
    # shortened to save space
    assert r["result"][:3] == aggreg_over_category_code_expected, fjd(r)


def test_aggregation_y_axis_category_code(client):
    # 1d data over a special column: category_code
    url = (
        "aggregation?probe_cc=IT&since=2021-07-09&until=2021-07-10&axis_y=category_code"
    )
    r = api(client, url)
    assert "dimension_count" in r, fjd(r)
    assert r["dimension_count"] == 1, fjd(r)
    # shortened to save space. The query should be identical to
    # test_aggregation_x_axis_category_code
    assert r["result"][:3] == aggreg_over_category_code_expected, fjd(r)


def test_aggregation_xy_axis_category_code(client):
    # 2d data over a special column: category_code
    url = "aggregation?since=2021-07-09&until=2021-07-10&axis_x=measurement_start_day&axis_y=category_code"
    r = api(client, url)
    assert "dimension_count" in r, fjd(r)
    assert r["dimension_count"] == 2, fjd(r)
    # shortened to save space. The query should be identical to
    # test_aggregation_x_axis_category_code
    expected_result = [
        {
            "anomaly_count": 0,
            "category_code": "GAME",
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 1,
            "measurement_start_day": "2021-07-09T00:00:00Z",
            "ok_count": 1,
        },
        {
            "anomaly_count": 0,
            "category_code": "GRP",
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 2,
            "measurement_start_day": "2021-07-09T02:00:00Z",
            "ok_count": 2,
        },
        {
            "anomaly_count": 0,
            "category_code": "GRP",
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 1,
            "measurement_start_day": "2021-07-09T03:00:00Z",
            "ok_count": 1,
        },
    ]
    assert r["result"][:3] == expected_result, fjd(r)


def test_aggregation_psiphon(client):
    url = "aggregation?probe_cc=MY&since=2024-01-01&until=2024-01-02&test_name=psiphon"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 0,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 1,
            "ok_count": 1,
        },
        "v": 0,
    }


def test_aggregation_input(client):
    url = "aggregation?since=2021-07-09&until=2021-07-10&input=https://twitter.com/"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 0,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 7,
            "ok_count": 7,
        },
        "v": 0,
    }


@pytest.mark.skip("TODO: fix the validation of inputs")
def test_aggregation_invalid_input(client):
    url = "aggregation?since=2021-07-09&until=2021-07-10&input=~!^{}"
    r = client.get(f"/api/v1/{url}")
    assert r.json() == {"msg": "Invalid characters in input field", "v": 0}


@pytest.mark.skip("TODO: fix the validation of inputs")
def test_aggregation_invalid_input_2(client):
    url = "aggregation?since=2021-07-09&until=2021-07-10&input=foo.org;"
    r = client.get(f"/api/v1/{url}")
    assert r.json() == {"msg": "Invalid characters in input field", "v": 0}


@pytest.mark.skip("TODO: fix the validation of inputs")
def test_aggregation_invalid_input_3(client):
    url = "aggregation?since=2021-07-09&until=2021-07-10&input=foo.org%3D%27"
    r = client.get(f"/api/v1/{url}")
    assert r.json() == {"msg": "Invalid characters in input field", "v": 0}


def test_aggregation_bug_585(client):
    url = "aggregation?test_name=web_connectivity&since=2022-01-24&until=2022-02-24&axis_x=measurement_start_day&category_code=LGBT"
    r = api(client, url)
    # TODO: figure out what this test should be validating and add some checks for it.

def test_aggregation_result_validation(client):
    """
    Validates that the probe_asn field in an Aggregation result of type int, not string
    """
    from oonimeasurements.routers.v1.aggregation import AggregationResult

    try:
        AggregationResult(anomaly_count=0, confirmed_count=0, failure_count=0, ok_count=0, measurement_count=0, probe_asn='bad')
    except pydantic.ValidationError:
        pass # ok

    # should not crash
    AggregationResult(anomaly_count=0, confirmed_count=0, failure_count=0, ok_count=0, measurement_count=0, probe_asn=1234)
