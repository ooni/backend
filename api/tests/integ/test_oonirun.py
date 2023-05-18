"""
Integration test for OONIRn API
"""


import pytest

from ..utils import api

# Automatically create required session fixtures
from .test_integration_auth import _register_and_login
from .test_integration_auth import reset_smtp_mock, setup_test_session

from .test_integration_auth import adminsession, usersession

# todo test with _nodb


@pytest.fixture
def cleanup():
    pass


def test_create_fetch_archive(cleanup, client, usersession, adminsession):
    # Reject empty name
    z = {
        "name": "",
        "description": "integ-test description",
        "icon": "",
        "author": "integ-test author",
        "nettests": [
            {
                "inputs": ["https://example.com/", "https://ooni.org/"],
                "options": {
                    "HTTP3Enabled": True,
                },
                "test_name": "web_connectivity",
            },
            {"test_name": "dnscheck"},
        ],
    }
    r = usersession.post("/api/_/ooni_run/create", json=z)
    assert r.status_code == 400, r.json

    z["name"] = "integ-test"
    r = usersession.post("/api/_/ooni_run/create", json=z)
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert str(r.json["id"]).endswith("00")
    oonirun_id = r.json["id"]

    # fetch latest
    r = usersession.get(f"/api/_/ooni_run/fetch/{oonirun_id}")
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert sorted(r.json) == ["creation_time", "descriptor", "v"]
    assert r.json["descriptor"] == z
    creation_time = r.json["creation_time"]
    assert creation_time.endswith("Z")

    # fetch by creation_time
    r = usersession.get(
        f"/api/_/ooni_run/fetch/{oonirun_id}?creation_time={creation_time}"
    )
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert sorted(r.json) == ["creation_time", "descriptor", "v"]
    assert r.json["descriptor"] == z
    assert creation_time == r.json["creation_time"]

    # list my items
    r = usersession.get(f"/api/_/ooni_run/list")
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert sorted(r.json) == ["descriptors", "v"]
    assert len(r.json["descriptors"]) > 0
    assert sorted(r.json["descriptors"][0]) == [
        "archived",
        "author",
        "creation_time",
        "description",
        "id",
        "mine",
        "name",
    ]

    # list all items as admin
    r = adminsession.get(f"/api/_/ooni_run/list")
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert sorted(r.json) == ["descriptors", "v"]
    assert len(r.json["descriptors"]) > 0
    assert sorted(r.json["descriptors"][0]) == [
        "archived",
        "author",
        "creation_time",
        "description",
        "id",
        "mine",
        "name",
    ]
    desc = [d for d in r.json["descriptors"] if d["id"] == oonirun_id]
    #  find the item created by usersession above
    assert desc[0]["name"] == "integ-test"

    # list all items as anonymous
    r = client.get(f"/api/_/ooni_run/list")
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert sorted(r.json) == ["descriptors", "v"]
    assert len(r.json["descriptors"]) > 0
    assert sorted(r.json["descriptors"][0]) == [
        "archived",
        "author",
        "creation_time",
        "description",
        "id",
        "name",
    ]
    #  find the item created by usersession above
    desc = [d for d in r.json["descriptors"] if d["id"] == oonirun_id][0]
    desc.pop("creation_time")
    desc.pop("id")
    assert desc == {
        "archived": 0,
        "author": "integ-test author",
        "description": "integ-test description",
        "name": "integ-test",
    }

    # "update" the oonirun by creating a new version
    r = usersession.post(f"/api/_/ooni_run/create?id={oonirun_id}", json=z)
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert r.json["id"] == oonirun_id

    # Fail to "update" the oonirun using the wrong account
    r = adminsession.post(f"/api/_/ooni_run/create?id={oonirun_id}", json=z)
    assert r.status_code == 400, r.json
    assert r.json == {"error": "OONIRun descriptor not found"}

    # archive
    r = usersession.post(f"/api/_/ooni_run/archive/{oonirun_id}")
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json


def test_fetch_not_found(cleanup, usersession):
    r = usersession.get(f"/api/_/ooni_run/fetch/999999999999999")
    assert r.status_code == 400, r.json
    assert r.json == {"error": "oonirun descriptor not found"}
