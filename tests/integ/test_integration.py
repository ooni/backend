"""
Integration test for API

Warning: this test runs against a real database
See README.adoc

Lint using:
    black -t py37 -l 100 --fast  tests/integ/test_integration.py

Test using:
    tox -e integ -- -s --show-capture=no -k test_aggregation
"""

from datetime import datetime, timedelta
from hashlib import shake_128
from textwrap import dedent
from urllib.parse import urlencode
import json
import os
import time

import pytest

from measurements.api.measurements import FASTPATH_MSM_ID_PREFIX

# The flask app is created in tests/conftest.py


def jd(o):
    return json.dumps(o, indent=2, sort_keys=True)


def fjd(o):
    # non-indented JSON dump
    return json.dumps(o, sort_keys=True)


@pytest.fixture()
def log(app):
    return app.logger


@pytest.fixture(autouse=True, scope="session")
def db_safety_check():
    assert os.environ["DATABASE_URL"] == "postgresql://readonly@localhost:15432/metadb"


@pytest.fixture()
def fastpath_dup_rid_input(app):
    """
    Access DB directly. Fetch > 1 measurements from fastpath that share the same
    report_id and input
    Returns (rid, input, count)
    """
    sql = """
    SELECT report_id, input,
    from fastpath
    group by report_id, input
    HAVING count(*) > 1
    LIMIT 1
    """
    with app.app_context():
        for row in app.db_session.execute(sql):
            return (row[0], row[1])


def dbquery(app, sql, **query_params):
    """Access DB directly, returns row as tuple.
    """
    with app.app_context():
        q = app.db_session.execute(sql, query_params)
        return q.fetchone()


@pytest.fixture()
def fastpath_rid_input(app):
    """Access DB directly. Get a fresh msmt that does not exists
    in the traditional pipeline yet
    Returns (rid, input)
    """
    if False:  # slow
        sql = """
        SELECT
            fastpath.report_id,
            fastpath.input
        FROM fastpath
        WHERE input IS NOT NULL
        AND fastpath.report_id IS NOT NULL
        AND NOT EXISTS (
            SELECT
            FROM report
            WHERE report.report_id = fastpath.report_id
        )
        LIMIT 1
        """
        rid, inp = dbquery(app, sql)[0:2]
        assert rid, repr(rid)
        assert rid.strip()
        assert inp
        assert inp.strip()
        return rid, inp

    sql = """
    SELECT report_id, input, test_start_time FROM fastpath
    WHERE input IS NOT NULL
    ORDER BY measurement_start_time DESC
    LIMIT 1
    """
    rid, inp, test_start_time = dbquery(app, sql)[0:3]
    assert rid.strip()
    assert inp.strip()

    check = """
    SELECT COUNT(report_id)
    FROM report
    WHERE report_id = '%s'
    """
    cnt = dbquery(app, check)[0]
    assert cnt == 0

    return (rid, inp, test_start_time)


@pytest.fixture()
def nonfastpath_rid_input(app):
    """Access DB directly. Get a random msmt
    Returns (rid, input)
    """
    sql = """
    SELECT report.report_id, input.input
    FROM measurement
    JOIN report ON report.report_no = measurement.report_no
    JOIN input ON input.input_no = measurement.input_no
    LIMIT 1
    """
    return dbquery(app, sql)[0:3]


@pytest.fixture()
def shared_rid_input(app):
    """Access DB directly. Get a random msmt that has a match both in the
    measurement and fastpath tables. Returns (rid, input)
    """
    sql = """
    SELECT
        fastpath.report_id,
        fastpath.input,
        test_start_time
    FROM fastpath
    WHERE input IS NOT NULL
    AND fastpath.report_id IS NOT NULL
    AND test_name = 'web_connectivity'
    AND EXISTS (
        SELECT
        FROM report
        WHERE report.report_id = fastpath.report_id
        AND report.test_start_time > :since
    )
    LIMIT 1
    """
    since = datetime.utcnow() - timedelta(days=3)
    rid, inp, test_start_time = dbquery(app, sql, since=since)[0:3]
    assert rid.strip()
    assert inp.strip()
    return rid, inp, test_start_time


@pytest.fixture()
def shared_rid_input_multi(app):
    """Access DB directly. Get a random msmt
    that has a match both in the measurement and fastpath tables
    Returns (rid, input)
    """
    sql = """
    SELECT
        fastpath.report_id,
        fastpath.input
    FROM fastpath
    WHERE input IS NOT NULL
    AND fastpath.test_start_time > :since
    AND fastpath.report_id IS NOT NULL
    AND test_name = 'web_connectivity'
    AND EXISTS (
        SELECT
        FROM report
        WHERE report.report_id = fastpath.report_id
        AND report.test_name = 'web_connectivity'
        AND report.test_start_time > :since
    )
    GROUP BY fastpath.report_id, fastpath.input
    HAVING count(*) > 1
    LIMIT 1
    """
    since = datetime.utcnow() - timedelta(days=3)
    rid, inp = dbquery(app, sql, since=since)[0:2]
    assert rid.strip()
    assert inp.strip()
    return rid, inp


@pytest.fixture()
def shared_rid_multi_input_null(app):
    """Access DB directly. Get a set of msmt that have a match both in the
    measurement and fastpath tables and input = NULL.
    Returns rid
    """
    sql = """
    SELECT
        fastpath.report_id
    FROM fastpath
    WHERE input IS NULL
    AND fastpath.test_start_time > :since
    AND fastpath.report_id IS NOT NULL
    AND test_name != 'web_connectivity'
    AND EXISTS (
        SELECT
        FROM report
        WHERE report.report_id = fastpath.report_id
        AND report.test_start_time > :since
    )
    GROUP BY fastpath.report_id, fastpath.input
    HAVING count(*) > 1
    LIMIT 1
    """
    since = datetime.utcnow() - timedelta(days=3)
    rid = dbquery(app, sql, since=since)[0]
    assert rid.strip()
    return rid


def api(client, subpath):
    response = client.get(f"/api/v1/{subpath}")
    assert response.status_code == 200
    assert response.is_json
    return response.json


def test_redirects_and_rate_limit_basic(client):
    # Simulate a forwarded client with a different ipaddr
    # In production the API sits behind Nginx
    headers = {"X-Real-IP": "1.2.3.4"}
    paths = (
        "/stats",
        "/files",
        "/files/by_date",
        "/api/_/test_names",
        "/api/_/test_names",
    )
    previous_remaining = 400
    for p in paths:
        resp = client.get(p, headers=headers)
        remaining = float(resp.headers["X-RateLimit-Remaining"])
        assert remaining < previous_remaining
        previous_remaining = remaining


def test_redirects_and_rate_limit_for_explorer(client):
    # Special ipaddr: no rate limiting. No header is set by the server
    headers = {"X-Real-IP": "37.218.242.149"}
    resp = client.get("/stats", headers=headers)
    assert resp.status_code == 301
    assert "X-RateLimit-Remaining" not in resp.headers

    resp = client.get("/stats", headers=headers)
    assert resp.status_code == 301
    assert "X-RateLimit-Remaining" not in resp.headers


def test_redirects_and_rate_limit_spin(client):
    # Simulate a forwarded client with a different ipaddr
    # In production the API sits behind Nginx
    limit = 400
    headers = {"X-Real-IP": "1.2.3.4"}
    t1 = time.monotonic() + 0.2
    while time.monotonic() < t1:
        resp = client.get("/stats", headers=headers)
    delta = time.monotonic() - t1
    assert 0 < delta < 0.3
    assert 0 < limit - float(resp.headers["X-RateLimit-Remaining"]) < 0.3


def test_redirects_and_rate_limit_summary(client):
    url = "quotas_summary"
    response = privapi(client, url)
    assert response == []
    response = privapi(client, url)
    assert len(response) == 1
    assert response[0][0] == 127  # first octet from 127.0.0.1
    assert int(response[0][1]) == 399  # quota remaining in seconds


# # list_files # #


def test_list_files_pagination(client):
    url = "files?limit=1&since=2019-12-01&until=2019-12-02"
    ret = api(client, url)
    results = ret["results"]
    assert len(results) == 1
    assert sorted(results[0].keys()) == [
        "download_url",
        "index",
        "probe_asn",
        "probe_cc",
        "test_name",
        "test_start_time",
    ]
    assert ret["metadata"] == {
        "count": 13273,
        "current_page": 1,
        "limit": 1,
        "next_url": "https://api.ooni.io/api/v1/files?limit=1&since=2019-12-01&until=2019-12-02&offset=1",
        "offset": 0,
        "pages": 13273,
    }
    url = "files?limit=1&since=2019-12-01&until=2019-12-02&offset=1"
    ret = api(client, url)
    results = ret["results"]
    assert len(results) == 1
    assert ret["metadata"] == {
        "count": 13273,
        "current_page": 2,
        "limit": 1,
        "next_url": "https://api.ooni.io/api/v1/files?limit=1&since=2019-12-01&until=2019-12-02&offset=2",
        "offset": 1,
        "pages": 13273,
    }


def test_list_files_asn(client):
    url = "files?limit=1&since=2019-12-01&until=2019-12-02&probe_asn=AS45595"
    results = api(client, url)["results"]
    assert len(results) == 1
    assert results[0]["probe_asn"] == "AS45595"


def test_list_files_asn_only_number(client):
    url = "files?limit=1&since=2019-12-01&until=2019-12-02&probe_asn=45595"
    results = api(client, url)["results"]
    assert len(results) == 1
    assert results[0]["probe_asn"] == "AS45595"


def test_list_files_range_cc(client):
    url = "files?limit=1000&since=2019-12-01&until=2019-12-02&probe_cc=IR"
    ret = api(client, url)
    results = ret["results"]
    assert len(results) == 215
    assert ret["metadata"] == {
        "count": 215,
        "current_page": 1,
        "limit": 1000,
        "next_url": None,
        "offset": 0,
        "pages": 1,
    }


def test_list_files_range_cc_asn(client):
    url = "files?limit=1000&since=2019-12-01&until=2019-12-02&probe_cc=IR&probe_asn=AS44375"
    results = api(client, url)["results"]
    assert len(results) == 7


# # list_measurements # #


def test_list_measurements(client):
    # A single measurement from 2017
    rid = "20171125T172144Z_AS45595_qutf6uDIgFxgJK6ROMElwgHJZxhibiBapLomWzzoNQhsP5KGW2"
    inp = "https://www.facebook.com"
    response = api(client, f"measurements?report_id={rid}&input={inp}")
    assert response["metadata"]["count"] == 1, jd(response)
    r = response["results"][0]
    assert r == {
        "anomaly": True,
        "confirmed": False,
        "failure": True,
        "input": "https://www.facebook.com",
        "measurement_id": "temp-id-138911420",
        "measurement_start_time": "2017-11-25T17:21:44Z",
        "measurement_url": "https://api.ooni.io/api/v1/measurement/temp-id-138911420",
        "probe_asn": "AS45595",
        "probe_cc": "PK",
        "report_id": "20171125T172144Z_AS45595_qutf6uDIgFxgJK6ROMElwgHJZxhibiBapLomWzzoNQhsP5KGW2",
        "scores": {},
        "test_name": "web_connectivity",
    }


def test_list_measurements_search(client):
    # Explorer is called with:
    # https://explorer.ooni.org/search?until=2019-12-05&domain=malaysia.msn.com&probe_cc=MM
    # ...leading to an API call to:
    # api.ooni.io/api/v1/measurements?probe_cc=MY&domain=malaysia.msn.com&until=2019-12-05&limit=50
    response = api(
        client, f"measurements?probe_cc=MY&domain=malaysia.msn.com&until=2019-12-05&limit=50",
    )
    assert len(response["results"]) == 50, jd(response)
    # assert response["metadata"]["count"] == 1, jd(response)


# # Benchmark list_measurements against traditional pipeline data  # #

# # Test slow list_measurements queries with order_by = None
# tox -q -e integ -- --durations=40 -k test_list_measurements_slow

# These are some of the parameters exposed by Explorer Search
@pytest.mark.timeout(20)
@pytest.mark.parametrize("probe_cc", ("YT", None))
@pytest.mark.parametrize("since", ("2017-01-01", None))
@pytest.mark.parametrize("test_name", ("web_connectivity", None))
@pytest.mark.parametrize("anomaly", ("true", None))
@pytest.mark.parametrize("domain", ("twitter.com", None))
@pytest.mark.skip(reason="This is too slow")
def test_list_measurements_slow_order_by_complete(
    domain, anomaly, test_name, since, probe_cc, log, client
):
    d = dict(
        probe_cc=probe_cc,
        since=since,
        test_name=test_name,
        anomaly=anomaly,
        domain=domain,
        until="2019-12-05",
    )
    d = {k: v for k, v in d.items() if v is not None}
    url = "measurements?" + urlencode(d)
    response = api(client, url)


@pytest.mark.parametrize("f", ("probe_cc=YT", "probe_asn=AS3352", "test_name=web_connectivity"))
def test_list_measurements_slow_order_by_group_1(f, log, client):
    # filter on probe_cc or probe_asn or test_name
    # order by --> "test_start_time"
    url = f"measurements?until=2019-01-01&{f}"
    log.info(url)
    response = api(client, url)


@pytest.mark.parametrize("f", ("anomaly=true", "domain=twitter.com"))
def test_list_measurements_slow_order_by_group_2(f, log, client):
    # anomaly or confirmed or failure or input or domain or category_code
    # order by --> "measurement_start_time"
    url = f"measurements?until=2019-01-01&{f}"
    log.info(url)
    response = api(client, url)


# This is the hard case. When mixing one filter that applies to the
# measurements table and one on the results table, there is no way to do
# an order_by that avoids heavy scans


@pytest.mark.parametrize("f1", ("probe_cc=YT", "test_name=web_connectivity"))
@pytest.mark.parametrize("f2", ("anomaly=true", "domain=twitter.com"))
def test_list_measurements_slow_order_by_group_3(f1, f2, log, client):
    url = f"measurements?until=2019-01-01&{f1}&{f2}"
    log.info(url)
    response = api(client, url)


def test_list_measurements_duplicate(client):
    # The API is now returning only one result
    rid = "20190720T201845Z_AS3352_Rmagvbg0ufqt8Q0kZBa5Hb0gIzfIBCgHb2PTw0VMLIuHn7mmZ4"
    inp = "http://www.linkedin.com/"
    response = api(client, f"measurements?report_id={rid}&input={inp}")
    assert response["metadata"]["count"] == 1, jd(response)


def test_list_measurements_pagination_old(client, log):
    # Ensure answers stay consistent across calls - using old data
    # https://github.com/ooni/api/issues/49
    url = "measurements?probe_cc=RU&test_name=web_connectivity&limit=100&offset=5000&since=2018-12-24&until=2018-12-25"
    j = None
    for n in range(3):
        log.info(f"{'-' * 20} Cycle {n} {'-' * 20}")
        new = api(client, url)
        del new["metadata"]["query_time"]
        if j is not None:
            assert j == new
        j = new


def test_list_measurements_pagination_new(client, log):
    # Ensure answers stay consistent across calls - using fresh data
    # https://github.com/ooni/api/issues/49
    since = (datetime.utcnow().date() - timedelta(days=1)).strftime("%Y-%m-%d")
    until = datetime.utcnow().date().strftime("%Y-%m-%d")
    url = f"measurements?probe_cc=RU&test_name=web_connectivity&limit=100&offset=5000&since={since}&until={until}"
    j = None
    for n in range(3):
        log.info(f"{'-' * 20} Cycle {n} {'-' * 20}")
        new = api(client, url)
        del new["metadata"]["query_time"]
        if j is not None:
            assert j == new
        j = new


def test_list_measurements_fastpath(client, fastpath_rid_input):
    """Get a fresh msmt from fastpath
    """
    rid, inp, test_start_time = fastpath_rid_input
    p = f"measurements?report_id={rid}&input={inp}"
    response = api(client, p)
    # This has collisions with data in the traditional pipeline
    assert response["metadata"]["count"] > 0, jd(response)


def today_range():
    """Return since/until pair to extract fresh fastpath entries"""
    since = datetime.utcnow().date()
    until = since + timedelta(days=1)
    return since, until


@pytest.mark.parametrize("anomaly", (True, False))
@pytest.mark.parametrize("confirmed", (True, False))
@pytest.mark.parametrize("failure", (True, False))
def test_list_measurements_filter_flags_fastpath(anomaly, confirmed, failure, client, log):
    """Test filtering by anomaly/confirmed/msm_failure using the cartesian product

    SELECT
    COUNT(*), anomaly, confirmed, msm_failure AS failure
FROM
    fastpath
WHERE
    measurement_start_time > '2020-01-13T00:00:00'::timestamp
    AND measurement_start_time <= '2020-01-14T00:00:00'::timestamp
    GROUP BY anomaly, confirmed, failure
    ORDER BY anomaly, confirmed, failure ASC;
  54412 | f       | f         | f
 156477 | f       | f         | t
  18679 | t       | f         | f
   6820 | t       | f         | t
    352 | t       | t         | f
   2637 | t       | t         | t
    """
    since, until = today_range()
    p = (
        f"measurements?since={since}&until={until}&anomaly={anomaly}"
        + f"&confirmed={confirmed}&failure={failure}&limit=100"
    )
    p = p.lower()
    log.info("Calling %s", p)
    response = api(client, p)
    for r in response["results"]:
        assert r["anomaly"] == anomaly, r
        assert r["confirmed"] == confirmed, r
        assert r["failure"] == failure, r

    i = anomaly * 4 + confirmed * 2 + failure * 1
    thresholds = [10, 100, 0, 0, 10, 10, 0, 10]
    assert len(response["results"]) >= thresholds[i]


# Notice: the decorators must be in inversed order
@pytest.mark.parametrize("failure", (True, False))
@pytest.mark.parametrize("confirmed", (True, False))
@pytest.mark.parametrize("anomaly", (True, False))
def test_list_measurements_filter_flags_pipeline(anomaly, confirmed, failure, client, log):
    """Test filtering by anomaly/confirmed/msm_failure using the cartesian product

    COUNT(*), anomaly, confirmed, measurement.exc IS NOT NULL AS failure
    FROM measurement
    WHERE
        measurement.measurement_start_time > '2019-01-01T00:00:00'::timestamp
        AND measurement.measurement_start_time <= '2019-02-01T00:00:00'::timestamp
        GROUP BY anomaly, confirmed, failure
        ORDER BY anomaly, confirmed, failure;
    """

    p = (
        f"measurements?since=2019-01-01&until=2019-02-01&anomaly={anomaly}"
        + f"&confirmed={confirmed}&failure={failure}&limit=100"
    )
    p = p.lower()
    log.info("Calling %s", p)
    response = api(client, p)
    for r in response["results"]:
        assert r["anomaly"] == anomaly, r
        assert r["confirmed"] == confirmed, r
        assert r["failure"] == failure, r

    if (anomaly, confirmed) == (False, True):
        # confirmed implies anomaly
        cnt = 0
    elif (anomaly, confirmed, failure) == (True, True, True):
        cnt = 1
    else:
        cnt = 100

    assert len(response["results"]) == cnt


def test_list_measurements_probe_asn(client):
    p = "measurements?probe_asn=AS3352&since=2019-12-8&until=2019-12-11&limit=50"
    response = api(client, p)
    assert len(response["results"]) == 50
    for r in response["results"]:
        assert r["probe_asn"] == "AS3352"


def test_list_measurements_failure_true_pipeline(client):
    p = "measurements?failure=true&since=2019-12-8&until=2019-12-11&limit=50"
    response = api(client, p)
    assert len(response["results"]) == 50
    for r in response["results"]:
        assert r["failure"] == True

    assert r["measurement_id"] == "temp-id-364725640"


def test_list_measurements_failure_false_pipeline(client):
    p = "measurements?failure=false&since=2019-12-8&until=2019-12-11&limit=50"
    response = api(client, p)
    assert len(response["results"]) == 50
    for r in response["results"]:
        assert r["failure"] == False, r

    assert r["measurement_id"] == "temp-id-364945592"


@pytest.mark.skip(reason="no way of currently testing this")
def test_list_measurements_failure_true_fastpath(client):
    since = datetime.utcnow().date()
    until = since + timedelta(days=1)
    p = f"measurements?failure=true&since={since}&until={until}&limit=50"
    response = api(client, p)
    assert len(response["results"]) == 50
    for r in response["results"]:
        assert r["failure"] == True, r


def test_list_measurements_failure_false_fastpath(client):
    since = datetime.utcnow().date()
    until = since + timedelta(days=1)
    p = f"measurements?failure=false&since={since}&until={until}&limit=50"
    response = api(client, p)
    assert len(response["results"]) == 50
    for r in response["results"]:
        assert r["failure"] == False, r


def test_list_measurements_shared(client, shared_rid_input, log):
    # A msmt both in mr_table and fastpath should have measurement_id from
    # mr_table and not from fastpath in order to use data from S3 and allow
    # deleting JSON files on the fastpath host
    rid, inp, test_start_time = shared_rid_input
    since = test_start_time
    until = since + timedelta(seconds=100)
    url = f"measurements?since={since}&until={until}&input={inp}&limit=5"
    response = api(client, url)
    results = [r for r in response["results"] if r["report_id"] == rid and r["input"] == inp]
    assert results
    for r in results:
        m = r["measurement_id"]
        assert "temp-fid" not in m
        assert "temp-id" in m


# category_code support: briefly tested by adding this to
# measurements/openapi/measurements.yml
# - name: category_code
#   in: query
#   type: string
#   minLength: 3
#   description: The category code to search measurements for
#
# def test_list_measurements_category_code(app, client):
#     p = "measurements?category_code=HACK&since=2019-12-8&until=2019-12-11&limit=50"
#     response = api(client, p)
#     assert len(response["results"]) == 50
#     for r in response["results"]:
#         print(r)


## get_measurement ##


def test_get_measurement(client):
    response = api(client, "measurement/temp-id-321045320")
    assert response["measurement_start_time"] == "2019-07-20 11:43:55", jd(response)
    assert response["probe_asn"] == "AS3352"
    assert response["probe_cc"] == "ES"
    assert (
        response["report_filename"]
        == "2019-07-20/20190717T115517Z-ES-AS3352-web_connectivity-20190720T201845Z_AS3352_Rmagvbg0ufqt8Q0kZBa5Hb0gIzfIBCgHb2PTw0VMLIuHn7mmZ4-0.2.0-probe.json"
    )
    assert len(response["test_keys"]["requests"][0]["response"]["body"]) == 72089


def test_get_measurement_missing_pipeline(client):
    url = "measurement/temp-id-999999999999999999"
    response = client.get(f"/api/v1/{url}")
    assert response.status_code == 404


@pytest.mark.get_measurement
def test_get_measurement_nonfastpath(client, nonfastpath_rid_input):
    """Simulate Explorer behavior
    Get a measurement from the traditional pipeline that has no match
    in the fastpath table
    """
    # Get a real rid/inp directly from the database
    rid, inp = nonfastpath_rid_input

    p = f"measurements?report_id={rid}&input={inp}"
    response = api(client, p)
    assert response["metadata"]["count"] > 0, jd(response)
    assert len(response["results"]) == 1, jd(response)
    pick = response["results"][0]
    assert "ent/temp-id-" in pick["measurement_url"]
    url = pick["measurement_url"]
    assert "anomaly" in pick, pick.keys()
    assert pick["scores"] == {}

    # Assure the correct msmt was received
    msm = api(client, url[27:])
    for f in ("probe_asn", "probe_cc", "report_id", "input", "test_name"):
        # (measurement_start_time differs in the timezone letter)
        assert msm[f] == pick[f], "%r field: %r != %r" % (f, msm[f], pick[f])


@pytest.mark.get_measurement
def test_get_measurement_fastpath(log, client, fastpath_rid_input):
    """Simulate Explorer behavior
    Get a measurement from the fastpath table that has no match in the
    traditional pipeline
    """
    # Get a real rid/inp directly from the database
    rid, inp, test_start_time = fastpath_rid_input

    # This has collisions with data from the traditional pipeline
    p = f"measurements?report_id={rid}&input={inp}"
    log.info("Calling API on %s", p)
    response = api(client, p)
    assert response["metadata"]["count"] > 0, jd(response)
    assert len(response["results"]) == 1, jd(response)
    pick = response["results"][0]
    url_substr = "measurement/{}".format(FASTPATH_MSM_ID_PREFIX)
    assert url_substr in pick["measurement_url"]
    assert "anomaly" in pick, pick.keys()
    assert pick["scores"] != {}
    assert "blocking_general" in pick["scores"]

    url = pick["measurement_url"]
    relurl = url[27:]
    log.info("Calling API on %r", relurl)
    msm = api(client, relurl)

    # Assure the correct msmt was received
    msm = api(client, relurl)
    for f in ("probe_asn", "probe_cc", "report_id", "input", "test_name"):
        # (measurement_start_time differs in the timezone letter)
        assert msm[f] == pick[f], "%r field: %r != %r" % (f, msm[f], pick[f])


# FIXME: test this with obfs4 as well
@pytest.mark.get_measurement
def test_get_measurement_joined_single(log, client, shared_rid_input):
    """Simulate Explorer behavior
    Get a measurement that has an entry in the fastpath table and also
    in the traditional pipeline
    """
    # Get a real rid/inp directly from the database
    rid, inp, _ = shared_rid_input

    # The rid/inp have entries both in fastpath and in the traditional pipeline
    p = f"measurements?report_id={rid}&input={inp}"
    log.info("Calling API on %s", p)
    response = api(client, p)
    assert response["metadata"]["count"] > 0, jd(response)
    assert len(response["results"]) == 1, jd(response)
    pick = response["results"][0]
    url_substr = "measurement/{}".format(FASTPATH_MSM_ID_PREFIX)
    assert url_substr in pick["measurement_url"]
    assert "anomaly" in pick, pick.keys()
    assert pick["scores"] != {}
    assert "blocking_general" in pick["scores"]

    url = pick["measurement_url"]
    relurl = url[27:]
    log.info("Calling API on %r", relurl)
    msm = api(client, relurl)

    # Assure the correct msmt was received
    msm = api(client, relurl)
    for f in ("probe_asn", "probe_cc", "report_id", "input", "test_name"):
        # (measurement_start_time differs in the timezone letter)
        assert msm[f] == pick[f], "%r field: %r != %r" % (f, msm[f], pick[f])


@pytest.mark.get_measurement
def test_get_measurement_joined_multi(log, client, shared_rid_input_multi):
    """Simulate Explorer behavior
    Get a measurement that has an entry in the fastpath table and also
    in the traditional pipeline
    """
    # Get a real rid/inp directly from the database
    rid, inp = shared_rid_input_multi

    # The rid/inp have entries both in fastpath and in the traditional pipeline
    p = f"measurements?report_id={rid}&input={inp}"
    log.info("Calling API on %s", p)
    response = api(client, p)
    assert response["metadata"]["count"] > 0, jd(response)
    assert len(response["results"]) == 1, jd(response)
    pick = response["results"][0]
    url_substr = "measurement/{}".format(FASTPATH_MSM_ID_PREFIX)
    assert url_substr in pick["measurement_url"]
    assert "anomaly" in pick, pick.keys()
    assert pick["scores"] != {}
    assert "blocking_general" in pick["scores"]

    url = pick["measurement_url"]
    relurl = url[27:]
    log.info("Calling API on %r", relurl)
    msm = api(client, relurl)

    # Assure the correct msmt was received
    msm = api(client, relurl)
    for f in ("probe_asn", "probe_cc", "report_id", "input", "test_name"):
        # (measurement_start_time differs in the timezone letter)
        assert msm[f] == pick[f], "%r field: %r != %r" % (f, msm[f], pick[f])


@pytest.mark.get_measurement
def test_get_measurement_joined_multi_input_null(log, client, shared_rid_multi_input_null):
    """Simulate Explorer behavior
    Get a measurement that has an entry in the fastpath table and also
    in the traditional pipeline
    """
    # Get a real rid directly from the database
    rid = shared_rid_multi_input_null
    assert isinstance(rid, str)

    # The rid has entries both in fastpath and in the traditional pipeline
    p = f"measurements?report_id={rid}"
    log.info("Calling API on %s", p)
    response = api(client, p)
    assert response["metadata"]["count"] > 0, jd(response)
    assert len(response["results"]) == 1, jd(response)
    pick = response["results"][0]
    assert pick["input"] is None

    url_substr = f"measurement/{FASTPATH_MSM_ID_PREFIX}"
    assert url_substr in pick["measurement_url"]
    assert "anomaly" in pick, pick.keys()
    assert pick["scores"] != {}
    assert "blocking_general" in pick["scores"]

    url = pick["measurement_url"]
    relurl = url[27:]
    log.info("Calling API on %r", relurl)
    msm = api(client, relurl)

    # Assure the correct msmt was received
    for f in ("probe_asn", "probe_cc", "report_id", "input", "test_name"):
        # (measurement_start_time differs in the timezone letter)
        assert msm[f] == pick[f], "%r field: %r != %r" % (f, msm[f], pick[f])


@pytest.mark.get_measurement
def test_bug_355_confirmed(client):
    # Use RU to have enough msmt
    p = "measurements?probe_cc=RU&limit=50&confirmed=true&since=2019-12-23&until=2019-12-24"
    response = api(client, p)
    for r in response["results"]:
        assert r["confirmed"] == True, r
    assert len(response["results"]) == 50


@pytest.mark.get_measurement
def test_bug_355_anomaly(client):
    p = "measurements?probe_cc=RU&limit=50&anomaly=true&since=2019-12-23&until=2019-12-24"
    response = api(client, p)
    for r in response["results"]:
        assert r["anomaly"] == True, r
    assert len(response["results"]) == 50


def test_bug_142_twitter(client):
    # we can assume there's always enough data
    ts = datetime.utcnow().date().strftime("%Y-%m-%d")
    p = "measurements?domain=twitter.com&until=%s&limit=20" % ts
    response = api(client, p)
    rows = tuple(response["results"])
    assert len(rows) == 20
    for r in rows:
        assert "twitter" in r["input"], r


def test_bug_278_with_input_none(client):
    url = "measurements?report_id=20190113T202156Z_AS327931_CgoC3KbgM6zKajvIIt1AxxybJ1HbjwwWJjsJnlxy9rpcGY54VH"
    response = api(client, url)
    assert response["metadata"]["count"] == 1, jd(response)
    assert response["results"] == [
        {
            "anomaly": False,
            "confirmed": False,
            "failure": False,
            "input": None,
            "measurement_id": "temp-id-263478291",
            "measurement_start_time": "2019-02-22T20:21:59Z",
            "measurement_url": "https://api.ooni.io/api/v1/measurement/temp-id-263478291",
            "probe_asn": "AS327931",
            "probe_cc": "DZ",
            "report_id": "20190113T202156Z_AS327931_CgoC3KbgM6zKajvIIt1AxxybJ1HbjwwWJjsJnlxy9rpcGY54VH",
            "scores": {},
            "test_name": "ndt",
        }
    ]


def test_bug_278_with_input_not_none(client):
    # Fetch web_connectivity by report_id only. Expect 25 hits where input
    # is backfilled from domain_input
    url = "measurements?report_id=20190221T235955Z_AS8346_GMKlfxcvS7Xcy2vPgzmOIxeJXnLdGmWVcZ18vrelaTQ4YDAUHo"
    response = api(client, url)
    assert response["metadata"]["count"] == 25, jd(response)
    for r in response["results"]:
        assert r["input"].startswith("http")


def test_bug_list_measurements_anomaly_coalesce(client):
    # list_measurements coalesce was giving priority to mr_table over fastpath
    url = "measurements?report_id=20200222T165239Z_AS24691_5WcQoZyep2HktNd8UvKf1Ka4C3WPyOc9AQP79zoJ7oPgyDwSWh"
    response = api(client, url)
    assert len(response["results"]) == 1
    r = response["results"][0]
    assert r["scores"]["blocking_general"] > 0.5
    assert not r["scores"]["analysis"]["whatsapp_endpoints_accessible"]

    assert not r["confirmed"]
    assert not r["failure"]
    assert r["anomaly"]


def test_list_measurements_external_order_by(client):
    # The last order-by on the rows from pipeline + fastpath
    today = datetime.utcnow().date()
    until = today + timedelta(days=1)
    url = f"measurements?until={until}&probe_cc=TR"
    response = api(client, url)
    last = max(r["measurement_start_time"] for r in response["results"])
    # Ensure that the newest msmt is from today (hence fastpath)
    assert last[:10] == str(today)
    assert len(response["results"]) == 100, jd(response)


def test_list_measurements_bug_probe1034(client):
    url = "measurements?report_id=blah"
    r = client.get(f"/api/v1/{url}", headers={"user-agent": "okhttp"})
    assert r.status_code == 200
    assert r.is_json
    response = r.json
    assert "results" in response
    assert len(response["results"]) == 1, repr(response)


def test_slow_inexistent_domain(client):
    # time-unbounded query, filtering by a domain never monitored
    p = "measurements?domain=meow.com&until=2019-12-11&limit=50"
    response = api(client, p)
    rows = tuple(response["results"])
    assert len(rows) == 0


def test_slow_domain_unbounded(client):
    # time-unbounded query, filtering by a popular domain
    p = "measurements?domain=twitter.com&until=2019-12-11&limit=50"
    response = api(client, p)
    rows = tuple(response["results"])
    assert rows


def test_slow_domain_bounded(client):
    p = "measurements?domain=twitter.com&since=2019-12-8&until=2019-12-11&limit=50"
    response = api(client, p)
    assert len(response["results"]) == 48


## files_download ##


def test_files_download_found(client):
    url = "files/download/2019-06-06/20190606T115021Z-IE-AS5466-ndt-20190606T115024Z_AS5466_fBGQoRbWb034yaEVz25JzTTge72KzFhcXValcZmIaQ8HWqy4Y1-0.2.0-probe.json"
    response = client.get(url)
    assert response.status_code == 200
    assert response.is_streamed
    data = response.get_data()
    assert shake_128(data).hexdigest(3) == "3e50c7"


def test_files_download_found_legacy(client):
    url = "files/download/20190606T115021Z-IE-AS5466-ndt-20190606T115024Z_AS5466_fBGQoRbWb034yaEVz25JzTTge72KzFhcXValcZmIaQ8HWqy4Y1-0.2.0-probe.json"
    response = client.get(url)
    assert response.status_code == 302


def test_files_download_missing(client):
    url = "files/download/2019-06-06/bogus-probe.json"
    response = client.get(url)
    assert response.status_code == 404


def test_files_download_missing_legacy(client):
    url = "files/download/without-slash-bogus-probe.json"
    response = client.get(url)
    assert response.status_code == 404


## private API ##


def privapi(client, subpath):
    response = client.get(f"/api/_/{subpath}")
    assert response.status_code == 200
    assert response.is_json
    return response.json


# TODO: improve tests


def test_private_api_asn_by_month(client):
    url = "asn_by_month"
    response = privapi(client, url)
    assert len(response) > 5
    r = response[0]
    assert sorted(r.keys()) == ["date", "value"]
    assert r["value"] > 10
    assert r["value"] < 10 ** 6


def test_private_api_countries_by_month(client):
    url = "countries_by_month"
    response = privapi(client, url)
    assert len(response) > 5
    r = response[0]
    assert sorted(r.keys()) == ["date", "value"]
    assert r["value"] > 10
    assert r["value"] < 1000


def test_private_api_runs_by_month(client):
    url = "runs_by_month"
    response = privapi(client, url)
    assert len(response) == 24
    assert sorted(response[0].keys()) == ["date", "value"]
    assert len(response[0]["date"]) == 10
    assert sum(i["value"] for i in response) > 6_000_000


def test_private_api_reports_per_day(client):
    url = "reports_per_day"
    response = privapi(client, url)
    assert len(response) > 2112
    assert sorted(response[0].keys()) == ["count", "date"]
    assert sum(i["count"] for i in response) > 6_000_000
    assert response[0] == {"count": 1, "date": "2003-11-06"}


def test_private_api_test_names(client, log):
    url = "test_names"
    response = privapi(client, url)
    assert response == {
        "test_names": [
            {"id": "web_connectivity", "name": "Web Connectivity"},
            {"id": "facebook_messenger", "name": "Facebook Messenger"},
            {"id": "telegram", "name": "Telegram"},
            {"id": "whatsapp", "name": "WhatsApp"},
            {"id": "http_invalid_request_line", "name": "HTTP Invalid Request Line"},
            {"id": "http_header_field_manipulation", "name": "HTTP Header Field Manipulation",},
            {"id": "ndt", "name": "NDT"},
            {"id": "dash", "name": "DASH"},
            {"id": "bridge_reachability", "name": "Bridge Reachability"},
            {"id": "meek_fronted_requests_test", "name": "Meek Fronted Requests"},
            {"id": "vanilla_tor", "name": "Vanilla Tor"},
            {"id": "tcp_connect", "name": "TCP Connect"},
            {"id": "http_requests", "name": "HTTP Requests"},
            {"id": "dns_consistency", "name": "DNS Consistency"},
            {"id": "http_host", "name": "HTTP Host"},
            {"id": "multi_protocol_traceroute", "name": "Multi Protocol Traceroute"},
        ]
    }


def test_private_api_countries(client, log):
    url = "countries"
    response = privapi(client, url)
    assert "countries" in response
    assert len(response["countries"]) == 232
    a = response["countries"][0]
    assert a["name"] == "Andorra"
    assert a["alpha_2"] == "AD"
    assert a["count"] > 100


# def test_private_api_test_coverage(client, log):
#     url = "test_coverage?probe_cc=US"
#     response = privapi(client, url)


# def test_private_api_website_networks(client, log):
#     url = "website_networks?probe_cc=US"
#     response = privapi(client, url)
#
#
# def test_private_api_website_stats(client, log):
#     url = "website_stats"
#     response = privapi(client, url)


def test_private_api_website_urls(client, log):
    url = "website_urls?probe_cc=BR&probe_asn=AS8167"
    response = privapi(client, url)
    r = response["metadata"]
    assert r["total_count"] > 0
    del r["total_count"]
    assert r == {
        "current_page": 1,
        "limit": 10,
        "next_url": "https://api.ooni.io/api/_/website_urls?probe_cc=BR&probe_asn=AS8167&offset=10&limit=10",
        "offset": 0,
    }
    assert len(response["results"]) > 1


# def test_private_api_vanilla_tor_stats(client):
#     url = "vanilla_tor_stats"
#     response = privapi(client, url)
#
#
# def test_private_api_im_networks(client):
#     url = "im_networks"
#     response = privapi(client, url)
#
#
# def test_private_api_im_stats(client):
#     url = "im_stats"
#     response = privapi(client, url)
#
#
# def test_private_api_network_stats(client):
#     url = "network_stats"
#     response = privapi(client, url)
#
#
# def test_private_api_country_overview(client):
#     url = "country_overview"
#     response = privapi(client, url)
#
#
# def test_private_api_global_overview(client):
#     url = "global_overview"
#     response = privapi(client, url)
#
#
# def test_private_api_global_overview_by_month(client):
#     url = "global_overview_by_month"
#     response = privapi(client, url)


# # aggregation # #


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


def test_aggregation_x_axis_y_axis(client, log):
    # 2-dimensional data
    url = "aggregation?since=2020-01-01&until=2020-02-01&axis_x=measurement_start_day&axis_y=probe_cc&test_name=web_connectivity"
    r = api(client, url)

    assert "error" not in r
    assert r["dimension_count"] == 2
    assert len(r["result"]) == 2140


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


def test_aggregation_x_axis_only_csv(client, log):
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


def test_aggregation_x_axis_category_code(client, log):
    # 1d data over a special column: category_code
    url = "aggregation?probe_cc=DE&since=2020-01-01&until=2020-01-03&axis_x=category_code"
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


def test_aggregation_y_axis_category_code(client, log):
    # 1d data over a special column: category_code
    url = "aggregation?probe_cc=DE&since=2020-03-01&until=2020-03-02&axis_y=category_code"
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
