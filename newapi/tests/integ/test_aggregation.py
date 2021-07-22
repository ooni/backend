import pytest

from textwrap import dedent
from urllib.parse import urlencode


def api(client, subpath, **kw):
    url = f"/api/v1/{subpath}"
    if kw:
        assert "?" not in url
        url += "?" + urlencode(kw)

    response = client.get(url)
    assert response.status_code == 200
    assert response.is_json
    return response.json


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_no_axis_with_caching(client, log):
    # 0-dimensional data
    url = "aggregation?probe_cc=BR&probe_asn=AS8167&since=2020-01-01&until=2020-02-01"
    response = client.get(f"/api/v1/{url}")
    assert response.status_code == 200
    assert response.is_json
    assert response.headers["Cache-Control"] == "max-age=86400"
    r = response.json
    expected = {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 13,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 350,
        },
        "v": 0,
    }
    assert r == expected, fjd(r)


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_no_axis_csv(client, log):
    # 0-dimensional data
    url = "aggregation?probe_cc=BR&probe_asn=AS8167&since=2020-01-01&until=2020-02-01&format=CSV"
    r = api(client, url)
    expected = dedent(
        """\
        anomaly_count,confirmed_count,failure_count,measurement_count
        13,0,0,350
    """
    )
    assert r.replace("\r", "") == expected


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_no_axis_domain(client):
    # 0-dimensional data
    url = "aggregation?probe_cc=IE&domain=twitter.com&since=2020-01-01&until=2020-01-03"
    r = api(client, url)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 0,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 236,
        },
        "v": 0,
    }, fjd(r)


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_no_axis_category_code(client):
    # 0-dimensional data
    url = "aggregation?probe_cc=IE&category_code=HACK&since=2020-01-01&until=2020-01-03"
    r = api(client, url)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 45,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 2538,
        },
        "v": 0,
    }, fjd(r)


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_x_axis_only(client, log):
    # 1 dimension: X
    url = "aggregation?probe_cc=BR&probe_asn=AS8167&since=2020-01-01&until=2020-01-05&axis_x=measurement_start_day"
    r = api(client, url)
    expected = {
        "dimension_count": 1,
        "result": [
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 5,
                "measurement_start_day": "2020-01-02",
            },
            {
                "anomaly_count": 1,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 37,
                "measurement_start_day": "2020-01-04",
            },
        ],
        "v": 0,
    }
    assert r == expected, fjd(r)


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_x_axis_only_category_code(client):
    # 1-dimensional data
    url = "aggregation?probe_cc=IE&category_code=HACK&since=2020-01-01&until=2020-01-03&axis_x=measurement_start_day"
    r = api(client, url)
    expected = {
        "dimension_count": 1,
        "result": [
            {
                "anomaly_count": 32,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 1302,
                "measurement_start_day": "2020-01-02",
            },
            {
                "anomaly_count": 13,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 1236,
                "measurement_start_day": "2020-01-03",
            },
        ],
        "v": 0,
    }
    assert r == expected, fjd(r)


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_x_axis_only_csv(client, log):
    # 1-dimensional data
    url = "aggregation?probe_cc=BR&probe_asn=AS8167&since=2020-01-01&until=2020-02-01&format=CSV&axis_x=measurement_start_day"
    r = api(client, url)
    expected = dedent(
        """\
        anomaly_count,confirmed_count,failure_count,measurement_count,measurement_start_day
        0,0,0,5,2020-01-02
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
    url = "aggregation?since=2020-01-01&until=2020-02-01&axis_x=measurement_start_day&axis_y=probe_cc&test_name=web_connectivity"
    r = api(client, url)

    assert "error" not in r
    assert r["dimension_count"] == 2
    assert len(r["result"]) == 2140


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_x_axis_y_axis_domain(client, log):
    # 2-dimensional data: day vs ASN
    url = "aggregation?probe_cc=DE&domain=twitter.com&since=2020-01-01&until=2020-01-03&axis_x=measurement_start_day&axis_y=probe_asn"
    r = api(client, url)
    assert r == {
        "dimension_count": 2,
        "result": [
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 4,
                "measurement_start_day": "2020-01-02",
                "probe_asn": 3320,
            },
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 4,
                "measurement_start_day": "2020-01-02",
                "probe_asn": 13184,
            },
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 1,
                "measurement_start_day": "2020-01-02",
                "probe_asn": 200052,
            },
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 4,
                "measurement_start_day": "2020-01-03",
                "probe_asn": 3209,
            },
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 5,
                "measurement_start_day": "2020-01-03",
                "probe_asn": 3320,
            },
            {
                "anomaly_count": 0,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 1,
                "measurement_start_day": "2020-01-03",
                "probe_asn": 9145,
            },
            {
                "anomaly_count": 4,
                "confirmed_count": 0,
                "failure_count": 0,
                "measurement_count": 4,
                "measurement_start_day": "2020-01-03",
                "probe_asn": 29562,
            },
        ],
        "v": 0,
    }, fjd(r)


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_x_axis_only_csv_2d(client, log):
    # 2-dimensional data: day vs ASN
    url = "aggregation?probe_cc=DE&domain=twitter.com&since=2020-01-01&until=2020-01-03&axis_x=measurement_start_day&axis_y=probe_asn&format=CSV"
    r = api(client, url)
    expected = dedent(
        """\
        anomaly_count,confirmed_count,failure_count,measurement_count,measurement_start_day,probe_asn
        0,0,0,4,2020-01-02,3320
        0,0,0,4,2020-01-02,13184
        0,0,0,1,2020-01-02,200052
        0,0,0,4,2020-01-03,3209
        0,0,0,5,2020-01-03,3320
        0,0,0,1,2020-01-03,9145
        4,0,0,4,2020-01-03,29562
    """
    )
    assert r.replace("\r", "") == expected


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_x_axis_category_code(client, log):
    # 1d data over a special column: category_code
    url = (
        "aggregation?probe_cc=DE&since=2020-01-01&until=2020-01-03&axis_x=category_code"
    )
    r = api(client, url)
    assert r["dimension_count"] == 1, fjd(r)
    # shortened to save space
    assert r["result"][:3] == [
        {
            "anomaly_count": 45,
            "category_code": "ALDR",
            "confirmed_count": 0,
            "failure_count": 1,
            "measurement_count": 261,
        },
        {
            "anomaly_count": 80,
            "category_code": "ANON",
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 423,
        },
        {
            "anomaly_count": 21,
            "category_code": "COMM",
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 107,
        },
    ], fjd(r)


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_y_axis_category_code(client, log):
    # 1d data over a special column: category_code
    url = (
        "aggregation?probe_cc=DE&since=2020-03-01&until=2020-03-02&axis_y=category_code"
    )
    r = api(client, url)
    assert "dimension_count" in r, fjd(r)
    assert r["dimension_count"] == 1, fjd(r)
    # shortened to save space. The query should be identical to
    # test_aggregation_x_axis_category_code
    assert r["result"][:3] == [
        {
            "anomaly_count": 45,
            "category_code": "ALDR",
            "confirmed_count": 0,
            "failure_count": 1,
            "measurement_count": 261,
        },
        {
            "anomaly_count": 80,
            "category_code": "ANON",
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 423,
        },
        {
            "anomaly_count": 21,
            "category_code": "COMM",
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 107,
        },
    ], fjd(r)


def test_aggregation_xy_axis_category_code(client, log):
    # 2d data over a special column: category_code
    url = "aggregation?since=2020-01-01&until=2020-01-03&axis_x=category_code&axis_y=category_code"
    r = api(client, url)
    assert "dimension_count" in r, fjd(r)
    assert r["dimension_count"] == 2, fjd(r)
    # shortened to save space. The query should be identical to
    # test_aggregation_x_axis_category_code
    assert r["result"][:3] == [], fjd(r)


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_tor(client):
    r = api(client, "aggregation?probe_cc=BY&since=2021-06-10T10:30:00&test_name=tor")
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 365,
            "confirmed_count": 0,
            "failure_count": 0,
            "measurement_count": 407,
        },
        "v": 0,
    }


def test_aggregation_test_name(client):
    r = client.get(f"/api/v1/aggregation?test_name=BOGUS")
    assert r.status_code == 400


@pytest.mark.skipif(not pytest.proddb, reason="use --proddb to run")
def test_aggregation_input(client):
    url = "aggregation?since=2020-01-01&until=2020-01-03&input=https://ccc.de/"
    r = api(client, url)
    assert r == {
        "dimension_count": 0,
        "result": {
            "anomaly_count": 23,
            "confirmed_count": 0,
            "failure_count": 21,
            "measurement_count": 319,
        },
        "v": 0,
    }
