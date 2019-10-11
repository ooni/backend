"""
Integration test for API

Warning: this test runs against a real database
See README.adoc
"""

import os
import json

import pytest

from measurements.api.measurements import FASTPATH_MSM_ID_PREFIX

# The flask app is created in tests/conftest.py
#
#

def jd(o):
    return json.dumps(o, indent=2, sort_keys=True)


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
    SELECT report_id, count(*)
    from fastpath
    WHERE input = 'http://www.ea.com'
    group by report_id
    HAVING count(*) > 1;
    """
    with app.app_context():
        for row in app.db_session.execute(sql):
            return (row[0], "http://www.ea.com", row[1])


def dbquery(app, sql):
    """Access DB directly, returns row as tuple.
    """
    with app.app_context():
        row = app.db_session.execute(sql).fetchone()
        return row


@pytest.fixture()
def fastpath_rid_input(app):
    """Access DB directly. Get a fresh msmt
    There's an infrequent race condition in case the record is deleted while
    the test runs.
    Returns (rid, input)
    """
    sql = """SELECT report_id, input FROM fastpath
    WHERE input IS NOT NULL
    ORDER BY measurement_start_time DESC
    LIMIT 1"""
    return dbquery(app, sql)[0:2]


@pytest.fixture()
def nonfastpath_rid_input(app):
    """Access DB directly. Get a random msmt
    Returns (rid, input)
    """
    sql = """SELECT report.report_id, input.input
        FROM measurement
        JOIN report ON report.report_no = measurement.report_no
        JOIN input ON input.input_no = measurement.input_no
        LIMIT 1
    """
    return dbquery(app, sql)[0:3]


def api(client, subpath):
    response = client.get(f"/api/v1/{subpath}")
    assert response.status_code == 200
    assert response.is_json
    return response.json


def test_list_measurements(client):
    # A single measurement from 2017
    rid = "20171125T172144Z_AS45595_qutf6uDIgFxgJK6ROMElwgHJZxhibiBapLomWzzoNQhsP5KGW2"
    inp = "https://www.facebook.com"
    response = api(client, f"measurements?report_id={rid}&input={inp}")
    assert response["metadata"]["count"] == 1, jd(response)


def test_list_measurements_duplicate(client):
    rid = "20190720T201845Z_AS3352_Rmagvbg0ufqt8Q0kZBa5Hb0gIzfIBCgHb2PTw0VMLIuHn7mmZ4"
    inp = "http://www.linkedin.com/"
    response = api(client, f"measurements?report_id={rid}&input={inp}")
    assert response["metadata"]["count"] >= 2, jd(response)


def test_list_measurements_pagination(client):
    # Ensure answers stay consistent
    # https://github.com/ooni/api/issues/49
    j = None
    for n in range(5):
        new = api(
            client,
            f"measurements?probe_cc=IR&test_name=web_connectivity&limit=100&offset=5000",
        )
        del new["metadata"]["query_time"]
        if j is not None:
            assert j == new
        j = new


def test_list_measurements_fastpath(client, fastpath_rid_input):
    """Get a fresh msmt from fastpath
    """
    rid, inp = fastpath_rid_input
    p = f"measurements?report_id={rid}&input={inp}"
    response = api(client, f"measurements?report_id={rid}&input={inp}")
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


def test_get_measurement_nonfastpath(client, nonfastpath_rid_input):
    """Simulate Explorer behavior
    """
    # Get a real rid/inp directly from the database
    rid, inp = nonfastpath_rid_input

    p = f"measurements?report_id={rid}&input={inp}"
    response = api(client, p)
    assert response["metadata"]["count"] > 0, jd(response)
    assert len(response["results"]) > 0, jd(response)

    pick = [r for r in response["results"] if "ent/temp-id-" in r["measurement_url"]]
    assert pick, "No result found in %s" % jd(response)
    # TODO: how does Explorer pick an entry?
    pick = pick[0]
    url = pick["measurement_url"]

    assert "anomaly" in pick, pick.keys()
    assert pick["scores"] == {}

    # Assure the correct msmt was received
    msm = api(client, url[27:])
    for f in ("probe_asn", "probe_cc", "report_id", "input","test_name"):
        # (measurement_start_time differs in the timezone letter)
        assert msm[f] == pick[f], "%r field: %r != %r" % (f, msm[f], pick[f])


def test_get_measurement_fastpath(client, fastpath_rid_input):
    """Simulate Explorer behavior
    """
    # Get a real rid/inp directly from the database
    rid, inp = fastpath_rid_input

    # This has collisions with data from the traditional pipeline
    p = f"measurements?report_id={rid}&input={inp}"
    response = api(client, p)
    assert response["metadata"]["count"] > 0, jd(response)
    assert len(response["results"]) > 0, jd(response)

    url_substr = "measurement/{}".format(FASTPATH_MSM_ID_PREFIX)
    pick = [r for r in response["results"] if url_substr in r["measurement_url"]]
    assert pick, "No fastpath result found in %s" % jd(response)
    pick = pick[0]

    assert "anomaly" in pick, pick.keys()
    assert pick["scores"] != {}

    url = pick["measurement_url"]
    msm = api(client, url[27:])

    # Assure the correct msmt was received
    msm = api(client, url[27:])
    for f in ("probe_asn", "probe_cc", "report_id", "input","test_name"):
        # (measurement_start_time differs in the timezone letter)
        assert msm[f] == pick[f], "%r field: %r != %r" % (f, msm[f], pick[f])
