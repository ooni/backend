"""
Integration test for API

Warning: this test runs against a real database
See README.adoc
"""

from datetime import datetime, timedelta
import json
import os

import pytest

from measurements.api.measurements import FASTPATH_MSM_ID_PREFIX

# The flask app is created in tests/conftest.py
#
#


def jd(o):
    return json.dumps(o, indent=2, sort_keys=True)


@pytest.fixture()
def log(app):
    return app.logger


@pytest.fixture(autouse=True, scope="session")
def db_safety_check():
    assert os.environ["DATABASE_URL"] == "postgresql://readonly@localhost:5433/metadb"


@pytest.fixture()
def fastpath_dup_rid_input(app):
    """
    Access DB directly
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


def dbquery(app, sql, *a):
    """Access DB directly, returns row as tuple.
    """
    with app.app_context():
        row = app.db_session.execute(sql, *a).fetchone()
        return row


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
    SELECT report_id, input FROM fastpath
    WHERE input IS NOT NULL
    ORDER BY measurement_start_time DESC
    LIMIT 1
    """
    rid, inp = dbquery(app, sql)[0:2]
    assert rid.strip()
    assert inp.strip()

    check = """
    SELECT COUNT(report_id)
    FROM report
    WHERE report_id = '%s'
    """
    cnt = dbquery(app, check)[0]
    assert cnt == 0

    return (rid, inp)


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
    AND fastpath.report_id IS NOT NULL
    AND EXISTS (
        SELECT
        FROM report
        WHERE report.report_id = fastpath.report_id
    )
    LIMIT 1
    """
    rid, inp = dbquery(app, sql)[0:2]
    assert rid.strip()
    assert inp.strip()
    return rid, inp


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
    AND fastpath.report_id IS NOT NULL
    AND EXISTS (
        SELECT
        FROM report
        WHERE report.report_id = fastpath.report_id
    )
    GROUP BY fastpath.report_id, fastpath.input
    HAVING count(*) > 1
    LIMIT 1
    """
    rid, inp = dbquery(app, sql)[0:2]
    assert rid.strip()
    assert inp.strip()
    return rid, inp


def api(client, subpath):
    response = client.get(f"/api/v1/{subpath}")
    assert response.status_code == 200
    assert response.is_json
    return response.json


def test_redirects_and_rate_limit(client):
    # Simulate a forwarded client with a different ipaddr
    # In production the API sits behind Nginx
    headers = {"X-Real-IP": "1.2.3.4"}
    limit = 400 - 1
    resp = client.get("/stats", headers=headers)
    assert resp.status_code == 301
    assert int(resp.headers["X-RateLimit-Remaining"]) == limit

    # Second GET: expect rate limiting decrease
    resp = client.get("/stats", headers=headers)
    assert resp.status_code == 301
    assert int(resp.headers["X-RateLimit-Remaining"]) == limit - 1

    resp = client.get("/files", headers=headers)
    assert resp.status_code == 301
    assert int(resp.headers["X-RateLimit-Remaining"]) == limit

    resp = client.get("/files/by_date", headers=headers)
    assert resp.status_code == 301
    assert int(resp.headers["X-RateLimit-Remaining"]) == limit


def test_redirects_and_rate_limit_for_explorer(client):
    # Special ipaddr: no rate limiting. No header is set by the server
    headers = {"X-Real-IP": "37.218.242.149"}
    resp = client.get("/stats", headers=headers)
    assert resp.status_code == 301
    assert "X-RateLimit-Remaining" not in resp.headers

    resp = client.get("/stats", headers=headers)
    assert resp.status_code == 301
    assert "X-RateLimit-Remaining" not in resp.headers


def test_list_measurements(client):
    # A single measurement from 2017
    rid = "20171125T172144Z_AS45595_qutf6uDIgFxgJK6ROMElwgHJZxhibiBapLomWzzoNQhsP5KGW2"
    inp = "https://www.facebook.com"
    response = api(client, f"measurements?report_id={rid}&input={inp}")
    assert response["metadata"]["count"] == 1, jd(response)


def test_list_measurements_search(client):
    # Explorer is called with:
    # https://explorer.ooni.org/search?until=2019-12-05&domain=malaysia.msn.com&probe_cc=MM
    # ...leading to an API call to:
    # api.ooni.io/api/v1/measurements?probe_cc=MY&domain=malaysia.msn.com&until=2019-12-05&limit=50
    response = api(
        client,
        f"measurements?probe_cc=MY&domain=malaysia.msn.com&until=2019-12-05&limit=50",
    )
    assert len(response["results"]) == 50, jd(response)
    # assert response["metadata"]["count"] == 1, jd(response)


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
    rid, inp = fastpath_rid_input
    p = f"measurements?report_id={rid}&input={inp}"
    response = api(client, p)
    # This has collisions with data in the traditional pipeline
    assert response["metadata"]["count"] > 0, jd(response)


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
def test_get_measurement_fastpath(app, client, fastpath_rid_input):
    """Simulate Explorer behavior
    Get a measurement from the fastpath table that has no match in the
    traditional pipeline
    """
    log = app.logger
    # Get a real rid/inp directly from the database
    rid, inp = fastpath_rid_input

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


@pytest.mark.get_measurement
def test_get_measurement_joined(app, client, shared_rid_input):
    """Simulate Explorer behavior
    Get a measurement that has an entry in the fastpath table and also
    in the traditional pipeline
    """
    log = app.logger
    # Get a real rid/inp directly from the database
    rid, inp = shared_rid_input

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
def test_get_measurement_joined_multi(app, client, shared_rid_input_multi):
    """Simulate Explorer behavior
    Get a measurement that has an entry in the fastpath table and also
    in the traditional pipeline
    """
    log = app.logger
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
def test_bug_355_confirmed(app, client):
    p = "measurements?probe_cc=IQ&limit=50&confirmed=true"
    response = api(client, p)
    for r in response["results"]:
        assert r["confirmed"] == True, r


@pytest.mark.get_measurement
def test_bug_355_anomaly(app, client):
    p = "measurements?probe_cc=IQ&limit=50&anomaly=true"
    response = api(client, p)
    for r in response["results"]:
        assert r["anomaly"] == True, r


def test_bug_142_twitter(app, client):
    # we can assume there's always enough data
    ts = datetime.utcnow().date().strftime("%Y-%m-%d")
    p = "measurements?domain=twitter.com&until=%s&limit=50" % ts
    response = api(client, p)
    rows = tuple(response["results"])
    assert len(rows) == 50
    for r in rows:
        assert "twitter" in r["input"], r


def test_slow_inexistent_domain(app, client):
    # time-unbounded query, filtering by a domain never monitored
    p = "measurements?domain=meow.com&until=2019-12-11&limit=50"
    response = api(client, p)
    rows = tuple(response["results"])
    assert len(rows) == 0


def test_slow_domain_unbounded(app, client):
    # time-unbounded query, filtering by a popular domain
    p = "measurements?domain=twitter.com&until=2019-12-11&limit=50"
    response = api(client, p)
    rows = tuple(response["results"])
    assert rows


def test_slow_domain_bounded(app, client):
    p = "measurements?domain=twitter.com&since=2019-12-8&until=2019-12-11&limit=50"
    response = api(client, p)
    assert len(response["results"]) == 48
