"""
Integration test for Incidents API
"""

from datetime import datetime

import pytest

from ..utils import api

# Automatically create required session fixtures
from .test_integration_auth import _register_and_login
from .test_integration_auth import reset_smtp_mock, setup_test_session

from .test_integration_auth import adminsession, usersession

# todo test with _nodb


@pytest.fixture
def cleanup(adminsession):
    r = adminsession.get("/api/v1/incidents/search")
    assert r.status_code == 200, r.json
    assert "incidents" in r.json
    for i in r.json["incidents"]:
        if i["title"] not in ("integ-test-1", "integ-test-2"):
            continue
        if i["reported_by"] != "ooni":
            continue

        j = dict(id=i["id"])
        r = adminsession.post("/api/v1/incidents/delete", json=j)
        assert r.status_code == 200, r.json


def test_crud_general(cleanup, client, adminsession, usersession):
    # Create
    new = dict(
        start_time=datetime(2020, 1, 1),
        end_time=None,
        reported_by="ooni",
        email_address="nick@localhost.local",
        title="integ-test-1",
        short_description="integ test",
        text="foo bar\nbaz\n",
        event_type="incident",
        published=False,
        CCs=["UK", "FR"],
        ASNs=[1, 2],
        domains=[],
        tags=["integ-test"],
        test_names=["web_connectivity", "signal"],
        links=[
            "https://explorer.ooni.org/chart/mat?test_name=web_connectivity&axis_x=measurement_start_day&since=2023-04-16&until=2023-05-16&time_grain=day"
        ],
    )
    d = dict(**new)
    r = adminsession.post("/api/v1/incidents/create", json=d)
    assert r.status_code == 200, r.json
    assert r.json["r"] == 1
    assert sorted(r.json) == ["id", "r"]
    incident_id = r.json["id"]

    # Show
    r = adminsession.get(f"/api/v1/incidents/show/{incident_id}")
    assert r.status_code == 200, r.json
    i = r.json["incident"]
    i.pop("update_time")
    # contains text
    expected = {
        "ASNs": [1, 2],
        "CCs": ["UK", "FR"],
        "text": "foo bar\nbaz\n",
        "domains": [],
        "end_time": None,
        "id": incident_id,
        "links": [
            "https://explorer.ooni.org/chart/mat?test_name=web_connectivity&axis_x=measurement_start_day&since=2023-04-16&until=2023-05-16&time_grain=day"
        ],
        "published": False,
        "reported_by": "ooni",
        "email_address": "nick@localhost.local",
        "start_time": "2020-01-01T00:00:00Z",
        "tags": ["integ-test"],
        "title": "integ-test-1",
        "short_description": "integ test",
        "test_names": ["web_connectivity", "signal"],
        "event_type": "incident",
        "mine": 1,
    }
    assert i == expected

    expected.pop("text")

    # Search as admin
    r = adminsession.get("/api/v1/incidents/search")
    assert r.status_code == 200, r.json
    i = [i for i in r.json["incidents"] if i["title"] == "integ-test-1"]
    i = i[0]
    assert i
    i.pop("update_time")
    assert i == expected

    # Search as anon - non-published incidents are not listed
    j = api(client, "incidents/search")
    assert len(j["incidents"]) == 0, r.json

    # Search as user - only_mine - finds nothing
    r = usersession.get("/api/v1/incidents/search?only_mine=True")
    assert r.status_code == 200, r.json
    assert r.json == {"incidents": [], "v": 1}

    # User cannot update due to ownership
    new["start_time"] = start_time = datetime(2020, 1, 7)
    new["id"] = incident_id
    d = dict(**new)
    r = usersession.post("/api/v1/incidents/update", json=d)
    assert r.status_code == 400, r.json

    # User cannot delete due to ownership
    d = dict(**new)
    r = usersession.post("/api/v1/incidents/delete", json=d)
    assert r.status_code == 400, r.json

    # Update as admin (change start_time and publish)
    new["start_time"] = datetime(2020, 1, 2)
    new["published"] = True
    d = dict(**new)
    r = adminsession.post("/api/v1/incidents/update", json=d)
    assert r.status_code == 200, r
    assert r.json["r"] == 1

    # Search as anon - now the incident shows up
    j = api(client, "incidents/search")
    assert "incidents" in j
    i = [i for i in j["incidents"] if i["title"] == "integ-test-1"]
    i = i[0]
    assert i
    i.pop("update_time")
    expected["start_time"] = "2020-01-02T00:00:00Z"
    expected["published"] = True
    expected["mine"] = 0
    assert i == expected

    # Delete as admin
    d = dict(**new)
    r = adminsession.post("/api/v1/incidents/delete", json=d)
    assert r.status_code == 200, r.json

    # Search as anon - finds nothing
    j = api(client, "incidents/search")
    assert j == {"incidents": [], "v": 1}

    # Search as user - only_mine - finds nothing
    r = usersession.get("/api/v1/incidents/search?only_mine=True")
    assert r.status_code == 200, r.json
    assert r.json == {"incidents": [], "v": 1}


def test_crud_user_create(cleanup, client, adminsession, usersession):
    title = "integ-test-2"
    new = dict(
        start_time=datetime(2020, 1, 1),
        end_time=None,
        reported_by="ooni",
        email_address="nick@localhost.local",
        title=title,
        short_description="integ test",
        text="foo bar\nbaz\n",
        event_type="incident",
        published=False,
        CCs=["UK", "FR"],
        test_names=["web_connectivity"],
        ASNs=[1, 2],
        domains=[],
        tags=["integ-test"],
        links=[
            "https://explorer.ooni.org/chart/mat?test_name=web_connectivity&axis_x=measurement_start_day&since=2023-04-16&until=2023-05-16&time_grain=day"
        ],
    )
    d = dict(**new)
    r = usersession.post("/api/v1/incidents/create", json=d)
    assert r.status_code == 200, r.json
    assert r.json["r"] == 1
    assert sorted(r.json) == ["id", "r"]
    incident_id = r.json["id"]

    # Search as user - only_mine - finds
    r = usersession.get("/api/v1/incidents/search?only_mine=True")
    assert r.status_code == 200, r.json
    i = [i for i in r.json["incidents"] if i["title"] == title][0]
    i.pop("update_time")
    i.pop("id")
    expected = {
        "ASNs": [1, 2],
        "CCs": ["UK", "FR"],
        "domains": [],
        "end_time": None,
        "links": [
            "https://explorer.ooni.org/chart/mat?test_name=web_connectivity&axis_x=measurement_start_day&since=2023-04-16&until=2023-05-16&time_grain=day"
        ],
        "published": False,
        "reported_by": "ooni",
        "email_address": "nick@localhost.local",
        "start_time": "2020-01-01T00:00:00Z",
        "tags": ["integ-test"],
        "title": title,
        "short_description": "integ test",
        "test_names": ["web_connectivity"],
        "mine": 1,
        "event_type": "incident",
    }
    assert i == expected


def test_crud_user_create_cannot_publish(cleanup, client, adminsession, usersession):
    # Create. Users attempts to publish the incident but is prevented.
    title = "integ-test-3"
    new = dict(
        start_time=datetime(2020, 1, 1),
        end_time=None,
        reported_by="ooni",
        email_address="nick@localhost.local",
        title=title,
        text="foo bar\nbaz\n",
        event_type="incident",
        published=True,
        CCs=["UK", "FR"],
        test_names=["web_connectivity"],
        ASNs=[1, 2],
        domains=[],
        tags=["integ-test"],
        links=[
            "https://explorer.ooni.org/chart/mat?test_name=web_connectivity&axis_x=measurement_start_day&since=2023-04-16&until=2023-05-16&time_grain=day"
        ],
    )
    d = dict(**new)
    r = usersession.post("/api/v1/incidents/create", json=d)
    assert r.status_code == 400, r.json


def test_crud_user_create_invalid_asns(cleanup, client, adminsession, usersession):
    title = "integ-test-4"
    new = dict(
        start_time=datetime(2020, 1, 1),
        end_time=None,
        reported_by="ooni",
        email_address="nick@localhost.local",
        title=title,
        text="foo bar\nbaz\n",
        event_type="incident",
        published=False,
        CCs=["UK", "FR"],
        test_names=["web_connectivity"],
        ASNs=[1, 2, "foo"],
        domains=[],
        tags=["integ-test"],
        links=[
            "https://explorer.ooni.org/chart/mat?test_name=web_connectivity&axis_x=measurement_start_day&since=2023-04-16&until=2023-05-16&time_grain=day"
        ],
    )
    d = dict(**new)
    r = usersession.post("/api/v1/incidents/create", json=d)
    assert r.status_code == 400, r.json


def test_crud_user_create_invalid_dates(cleanup, client, adminsession, usersession):
    title = "integ-test-5"
    new = dict(
        start_time=datetime(2020, 1, 1),
        end_time=datetime(2019, 1, 1),
        reported_by="ooni",
        email_address="nick@localhost.local",
        title=title,
        text="foo bar\nbaz\n",
        event_type="incident",
        published=False,
        CCs=["UK", "FR"],
        test_names=["web_connectivity"],
        ASNs=[1, 2],
        domains=[],
        tags=["integ-test"],
        links=[
            "https://explorer.ooni.org/chart/mat?test_name=web_connectivity&axis_x=measurement_start_day&since=2023-04-16&until=2023-05-16&time_grain=day"
        ],
    )
    d = dict(**new)
    r = usersession.post("/api/v1/incidents/create", json=d)
    assert r.status_code == 400, r.json


def test_crud_user_create_mismatched_email(cleanup, client, adminsession, usersession):
    title = "integ-test-6"
    new = dict(
        start_time=datetime(2020, 1, 1),
        end_time=None,
        reported_by="ooni",
        email_address="WRONG_ADDRESS@localhost.local",
        title=title,
        short_description="integ test",
        text="foo bar\nbaz\n",
        event_type="incident",
        published=False,
        CCs=["UK", "FR"],
        test_names=["web_connectivity"],
        ASNs=[1, 2],
        domains=[],
        tags=["integ-test"],
        links=[
            "https://explorer.ooni.org/chart/mat?test_name=web_connectivity&axis_x=measurement_start_day&since=2023-04-16&until=2023-05-16&time_grain=day"
        ],
    )
    d = dict(**new)
    r = usersession.post("/api/v1/incidents/create", json=d)
    assert r.status_code == 400, r.json


def test_crud_invalid_fields(client, adminsession, usersession):
    # Create
    new = dict(
        start_time=datetime(2020, 1, 1),
        end_time=None,
        reported_by="ooni",
        email_address="nick@localhost.local",
        title="",  # empty
        short_description="integ test",
        text="foo bar\nbaz\n",
        event_type="incident",
        published=False,
        CCs=["UK", "FR"],
        ASNs=[1, 2],
        domains=[],
        tags=["integ-test"],
        links=[
            "https://explorer.ooni.org/chart/mat?test_name=web_connectivity&axis_x=measurement_start_day&since=2023-04-16&until=2023-05-16&time_grain=day"
        ],
    )
    d = dict(new_entry=new)
    r = adminsession.post("/api/v1/incidents/update", json=d)
    assert r.status_code == 400, r.json


def test_crud_extra_field(client, adminsession, usersession):
    # Create
    new = dict(
        BOGUS_UNEXPECTED=1,
        start_time=datetime(2020, 1, 1),
        end_time=None,
        reported_by="ooni",
        email_address="nick@localhost.local",
        title="",
        short_description="integ test",
        text="foo bar\nbaz\n",
        event_type="incident",
        published=False,
        CCs=["UK", "FR"],
        ASNs=[1, 2],
        domains=[],
        tags=["integ-test"],
        links=[
            "https://explorer.ooni.org/chart/mat?test_name=web_connectivity&axis_x=measurement_start_day&since=2023-04-16&until=2023-05-16&time_grain=day"
        ],
    )
    d = dict(new_entry=new)
    r = adminsession.post("/api/v1/incidents/update", json=d)
    assert r.status_code == 400, r.json
