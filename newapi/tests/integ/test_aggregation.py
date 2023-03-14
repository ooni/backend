import pytest

from textwrap import dedent
from urllib.parse import urlencode
from ..utils import fjd


def api(client, subpath, **kw):
    url = f"/api/v1/{subpath}"
    if kw:
        assert "?" not in url
        url += "?" + urlencode(kw)

    response = client.get(url)
    assert response.status_code == 200, response.data
    assert response.is_json
    return response.json


def test_aggregation_no_axis_with_caching(client, log):
    # 0-dimensional data
    url = "aggregation?probe_cc=CH&probe_asn=AS3303&since=2021-07-09&until=2021-07-10"
    resp = client.get(f"/api/v1/{url}")
    assert resp.status_code == 200
    assert resp.is_json
    r = resp.json
    r.pop("db_stats", None)
    expected = {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 187,
            "confirmed_count": 0,
            "failure_count": 5,
            "measurement_count": 1689,
            "ok_count": 1497,
        },
        "v": 0,
    }
    assert r == expected, fjd(r)
    h = dict(resp.headers)
    # FIXME: caching is currently disabled
    # assert h["Cache-Control"] == "max-age=86400"


def test_aggregation_no_axis_csv(client, log):
    # 0-dimensional data
    url = "aggregation?probe_cc=CH&probe_asn=AS3303&since=2021-07-09&until=2021-07-10&format=CSV"
    r = client.get(f"/api/v1/{url}")
    assert not r.is_json
    expected = dedent(
        """\
        anomaly_count,confirmed_count,failure_count,measurement_count,ok_count
        187,0,5,1689,1497
    """
    )
    assert r.data.decode().replace("\r", "") == expected
    assert r.content_type == "text/csv"
    assert "Content-Disposition" not in r.headers  # not a download


def test_aggregation_no_axis_csv_dload(client, log):
    # 0-dimensional data
    url = "aggregation?probe_cc=CH&probe_asn=AS3303&since=2021-07-09&until=2021-07-10&format=CSV&download=true"
    r = client.get(f"/api/v1/{url}")
    assert not r.is_json
    assert r.content_type == "text/csv"
    exp = "attachment; filename=ooni-aggregate-data.csv"
    assert r.headers["Content-Disposition"] == exp


def test_aggregation_no_axis_domain(client):
    # 0-dimensional data
    url = "aggregation?probe_cc=BR&domain=www.cabofrio.rj.gov.br&since=2021-07-09&until=2021-07-10"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 21,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 21,
            "ok_count": 0,
        },
        "v": 0,
    }, fjd(r)


def test_aggregation_no_axis_domain_ipaddr(client):
    # 0-dimensional data
    url = "aggregation?domain=8.8.4.4&since=2021-07-01&until=2021-07-10"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 1,
            "confirmed_count": 0,
            "failure_count": 1,
            "measurement_count": 10,
            "ok_count": 8,
        },
        "v": 0,
    }, fjd(r)


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


def test_aggregation_no_axis_filter_by_category_code(client):
    # 0-dimensional data
    url = (
        "aggregation?probe_cc=BR&category_code=CULTR&since=2021-07-09&until=2021-07-10"
    )
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 0,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 14,
            "ok_count": 14,
        },
        "v": 0,
    }, fjd(r)


def test_aggregation_x_axis_only(client, log):
    # 1 dimension: X
    url = "aggregation?probe_cc=CH&probe_asn=AS3303&since=2021-07-09&until=2021-07-11&time_grain=day&axis_x=measurement_start_day"
    r = api(client, url)
    r.pop("db_stats", None)
    expected = {
        "dimension_count": 1,
        "result": [
            {
                "anomaly_count": 187,
                "confirmed_count": 0,
                "failure_count": 5,
                "measurement_count": 1689,
                "measurement_start_day": "2021-07-09",
                "ok_count": 1497,
            },
        ],
        "v": 0,
    }
    assert r == expected, fjd(r)


def test_aggregation_x_axis_only_invalid_range(client, log):
    # 1 dimension: X
    url = "aggregation?since=2022-07-09&until=2021-07-11&time_grain=day&axis_x=measurement_start_day"
    r = client.get(f"/api/v1/{url}")
    assert r.status_code == 400


def test_aggregation_x_axis_only_invalid_time_grain_too_small(client, log):
    # 1 dimension: X
    url = "aggregation?since=2020-07-09&until=2022-07-11&time_grain=hour&axis_x=measurement_start_day"
    r = client.get(f"/api/v1/{url}")
    assert r.status_code == 400
    exp = "Choose time_grain between day, week, month, year, auto for the given time range"
    assert r.json["error"] == exp


def test_aggregation_x_axis_only_invalid_time_grain_too_large(client, log):
    # 1 dimension: X
    url = "aggregation?since=2022-07-09&until=2022-07-11&time_grain=year&axis_x=measurement_start_day"
    r = client.get(f"/api/v1/{url}")
    assert r.status_code == 400
    exp = "Choose time_grain between hour, day, auto for the given time range"
    assert r.json["error"] == exp


def test_aggregation_x_axis_only_hour(client, log):
    # 1 dimension: X
    url = "aggregation?since=2021-07-09&until=2021-07-11&axis_x=measurement_start_day"
    r = api(client, url)
    r.pop("db_stats", None)
    expected = {
        "dimension_count": 1,
        "result": [
            {
                "anomaly_count": 688,
                "confirmed_count": 42,
                "failure_count": 720,
                "measurement_count": 9990,
                "measurement_start_day": "2021-07-09T00:00:00Z",
                "ok_count": 8540,
            },
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 1,
                "measurement_start_day": "2021-07-09T01:00:00Z",
                "ok_count": 1,
            },
        ],
        "v": 0,
    }
    assert r == expected, fjd(r)


def test_aggregation_x_axis_domain(client, log):
    # 1 dimension: X
    url = "aggregation?probe_cc=CH&probe_asn=AS3303&since=2021-07-09&until=2021-07-10&axis_x=domain"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r["dimension_count"] == 1
    for x in r["result"]:
        if x["domain"] == "www.theregister.co.uk":
            assert x == {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "domain": "www.theregister.co.uk",
                "failure_count": 0,
                "measurement_count": 1,
                "ok_count": 1,
            }
            return

    assert False, "Msmt not found"


@pytest.mark.skip("To be fixed in future")
def test_aggregation_y_axis_only_blocking_type(client, log):
    # 1 dimension: Y: blocking_type
    url = "aggregation?since=2021-07-09&until=2021-07-10&axis_y=blocking_type"
    r = api(client, url)
    r.pop("db_stats", None)
    expected = {
        "dimension_count": 1,
        "result": [
            # FIXME
        ],
        "v": 0,
    }
    assert r == expected, fjd(r)


def test_aggregation_x_axis_only_probe_cc(client, log):
    # 1 dimension: X
    url = "aggregation?since=2021-07-09&until=2021-07-10&axis_x=probe_cc"
    r = api(client, url)
    assert r["dimension_count"] == 1
    assert len(r["result"]) == 33


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_x_axis_only_category_code(client):
    # 1-dimensional data
    url = "aggregation?probe_cc=IE&category_code=HACK&since=2021-07-09&until=2021-07-10&axis_x=measurement_start_day"
    r = api(client, url)
    expected = {
        "dimension_count": 1,
        "result": [
            {
                "anomaly_count": 32,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 1302,
                "measurement_start_day": "2021-07-10",
            },
            {
                "anomaly_count": 13,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 1236,
                "measurement_start_day": "2021-07-10",
            },
        ],
        "v": 0,
    }
    assert r == expected, fjd(r)


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_x_axis_only_csv(client, log):
    # 1-dimensional data
    url = "aggregation?probe_cc=BR&probe_asn=AS8167&since=2021-07-09&until=2021-07-10&format=CSV&axis_x=measurement_start_day"
    r = api(client, url)
    expected = dedent(
        """\
        anomaly_count,confirmed_count,failure_count,measurement_count,measurement_start_day
        0,0,0,5,2021-07-10
        1,0,0,37,2020-01-04
        2,0,0,46,2020-01-08
        2,0,0,26,2020-01-13
        0,0,0,20,2020-01-16
        2,0,0,87,2020-01-20
        0,0,0,6,2020-01-21
        6,0,0,87,2020-01-23
        0,0,0,11,2020-01-26
        0,0,0,25,2020-01-27
    """
    )
    assert r.replace("\r", "") == expected


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_x_axis_y_axis(client, log):
    # 2-dimensional data
    url = "aggregation?since=2021-07-09&until=2021-07-10&axis_x=measurement_start_day&axis_y=probe_cc&test_name=web_connectivity"
    r = api(client, url)

    assert "error" not in r
    assert r["dimension_count"] == 2
    assert len(r["result"]) == 2140


def test_aggregation_x_axis_y_axis_are_the_same(client, log):
    # 2-dimensional data
    url = "aggregation?since=2021-07-09&until=2021-07-10&axis_x=probe_cc&axis_y=probe_cc&test_name=web_connectivity"
    r = api(client, url)
    assert r == {"error": "Axis X and Y cannot be the same", "v": 0}


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_two_axis_too_big(client, log):
    url = "aggregation?since=2021-10-14&until=2021-10-15&test_name=web_connectivity&axis_x=measurement_start_day&axis_y=input"
    r = api(client, url)
    assert r == {}


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


def test_aggregation_x_axis_only_csv_2d(client, log):
    # 2-dimensional data: day vs ASN
    dom = "www.cabofrio.rj.gov.br"
    url = f"aggregation?probe_cc=BR&domain={dom}&since=2021-07-09&until=2021-07-10&time_grain=day&axis_x=measurement_start_day&axis_y=probe_asn&format=CSV"
    r = client.get(f"/api/v1/{url}")
    assert r.status_code == 200
    assert not r.is_json
    expected = dedent(
        """\
        anomaly_count,confirmed_count,failure_count,measurement_count,measurement_start_day,ok_count,probe_asn
        1,0,0,1,2021-07-09,0,18881
        1,0,0,1,2021-07-09,0,28154
        1,0,0,1,2021-07-09,0,28183
        1,0,0,1,2021-07-09,0,28210
        1,0,0,1,2021-07-09,0,28343
        3,0,0,3,2021-07-09,0,28573
        1,0,0,1,2021-07-09,0,53029
        1,0,0,1,2021-07-09,0,53089
        1,0,0,1,2021-07-09,0,53209
        1,0,0,1,2021-07-09,0,262616
        1,0,0,1,2021-07-09,0,262644
        1,0,0,1,2021-07-09,0,262970
        2,0,0,2,2021-07-09,0,262983
        1,0,0,1,2021-07-09,0,264146
        1,0,0,1,2021-07-09,0,264510
        1,0,0,1,2021-07-09,0,264592
        1,0,0,1,2021-07-09,0,268821
        1,0,0,1,2021-07-09,0,269246
    """
    )
    assert r.data.decode().replace("\r", "") == expected


aggreg_over_category_code_expected = [
    {
        "anomaly_count": 77,
        "category_code": "ALDR",
        "confirmed_count": 0,
        "failure_count": 116,
        "measurement_count": 250,
    },
    {
        "anomaly_count": 118,
        "category_code": "ANON",
        "confirmed_count": 0,
        "failure_count": 184,
        "measurement_count": 405,
    },
    {
        "anomaly_count": 35,
        "category_code": "COMM",
        "confirmed_count": 0,
        "failure_count": 54,
        "measurement_count": 107,
    },
]


@pytest.mark.skip("FIXME citizenlab")
def test_aggregation_x_axis_category_code(client, log):
    # 1d data over a special column: category_code
    url = (
        "aggregation?probe_cc=DE&since=2021-07-09&until=2021-07-10&axis_x=category_code"
    )
    r = api(client, url)
    assert r["dimension_count"] == 1, fjd(r)
    # shortened to save space
    assert r["result"][:3] == aggreg_over_category_code_expected, fjd(r)


# @pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
@pytest.mark.skip("FIXME citizenlab")
def test_aggregation_y_axis_category_code(client, log):
    # 1d data over a special column: category_code
    url = (
        "aggregation?probe_cc=DE&since=2021-07-09&until=2021-07-10&axis_y=category_code"
    )
    r = api(client, url)
    assert "dimension_count" in r, fjd(r)
    assert r["dimension_count"] == 1, fjd(r)
    # shortened to save space. The query should be identical to
    # test_aggregation_x_axis_category_code
    assert r["result"][:3] == aggreg_over_category_code_expected, fjd(r)


@pytest.mark.skip("FIXME citizenlab")
def test_aggregation_xy_axis_category_code(client, log):
    # 2d data over a special column: category_code
    url = "aggregation?since=2021-07-09&until=2021-07-10&axis_x=category_code&axis_y=category_code"
    r = api(client, url)
    assert "dimension_count" in r, fjd(r)
    assert r["dimension_count"] == 2, fjd(r)
    # shortened to save space. The query should be identical to
    # test_aggregation_x_axis_category_code
    assert r["result"][:3] == [], fjd(r)


def test_aggregation_psiphon(client):
    r = api(
        client,
        "aggregation?probe_cc=BR&since=2021-07-09&until=2021-07-10&test_name=psiphon",
    )
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 0,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 20,
            "ok_count": 20,
        },
        "v": 0,
    }


def test_aggregation_test_name(client):
    r = client.get(f"/api/v1/aggregation?test_name=BOGUS")
    assert r.status_code == 400


def test_aggregation_input(client):
    url = "aggregation?since=2021-07-09&until=2021-07-10&input=http://www.cabofrio.rj.gov.br/"
    r = api(client, url)
    r.pop("db_stats", None)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 21,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 21,
            "ok_count": 0,
        },
        "v": 0,
    }


def test_aggregation_invalid_input(client):
    url = "aggregation?since=2021-07-09&until=2021-07-10&input=~!^{}"
    r = api(client, url)
    assert r == {"error": "Invalid characters in input field", "v": 0}


def test_aggregation_invalid_input_2(client):
    url = "aggregation?since=2021-07-09&until=2021-07-10&input=foo.org;"
    r = api(client, url)
    assert r == {"error": "Invalid characters in input field", "v": 0}


def test_aggregation_invalid_input_3(client):
    url = "aggregation?since=2021-07-09&until=2021-07-10&input=foo.org%3D%27"
    r = api(client, url)
    assert r == {"error": "Invalid characters in input field", "v": 0}


def test_aggregation_bug_585(client):
    url = "aggregation?test_name=web_connectivity&since=2022-01-24&until=2022-02-24&axis_x=measurement_start_day&category_code=LGBT"
    r = api(client, url)
