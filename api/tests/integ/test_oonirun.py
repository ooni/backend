"""
Integration test for OONIRn API
"""


import pytest

# Automatically create required session fixtures
from .test_integration_auth import _register_and_login
from .test_integration_auth import reset_smtp_mock, setup_test_session

from .test_integration_auth import adminsession, usersession

import ooniapi

# todo test with _nodb


@pytest.fixture
def cleanup():
    pass


def test_create_fetch_archive(cleanup, client, usersession, adminsession):
    say = ooniapi.citizenlab.current_app.logger.say
    say("Reject empty name")
    z = {
        "name": "",
        "name_intl": {
            "it": "",
        },
        "description": "integ-test description in English",
        "description_intl": {
            "es": "integ-test descripción en español",
        },
        "short_description": "integ-test short description in English",
        "short_description_intl": {
            "it": "integ-test descrizione breve in italiano",
        },
        "icon": "myicon",
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
    say("Empty name")
    r = usersession.post("/api/_/ooni_run/create", json=z)
    assert r.status_code == 400, r.json

    say("Empty name_intl->it")
    z["name"] = "integ-test name in English"
    r = usersession.post("/api/_/ooni_run/create", json=z)
    assert r.status_code == 400, r.json

    ### Create descriptor as user
    z["name_intl"]["it"] = "integ-test nome in italiano"
    r = usersession.post("/api/_/ooni_run/create", json=z)
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert str(r.json["ooni_run_link_id"]).endswith("00")
    ooni_run_link_id = int(r.json["ooni_run_link_id"])

    say("fetch latest")
    r = usersession.get(f"/api/_/ooni_run/fetch/{ooni_run_link_id}")
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    exp_fetch_fields = [
        "archived",
        "descriptor",
        "descriptor_creation_time",
        "mine",
        "translation_creation_time",
        "v",
    ]
    assert sorted(r.json) == exp_fetch_fields
    exp = {
        "name": "integ-test name in English",
        "name_intl": {
            "it": "integ-test nome in italiano",
        },
        "description": "integ-test description in English",
        "description_intl": {
            "es": "integ-test descripción en español",
        },
        "short_description": "integ-test short description in English",
        "short_description_intl": {
            "it": "integ-test descrizione breve in italiano",
        },
        "icon": "myicon",
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
    assert r.json["descriptor"] == exp
    creation_time = r.json["descriptor_creation_time"]
    translation_creation_time = r.json["translation_creation_time"]
    assert creation_time.endswith("Z")

    say("fetch by creation_time")
    r = usersession.get(
        f"/api/_/ooni_run/fetch/{ooni_run_link_id}?creation_time={creation_time}"
    )
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert sorted(r.json) == exp_fetch_fields
    assert r.json["descriptor"] == exp
    assert creation_time == r.json["descriptor_creation_time"]
    assert translation_creation_time == r.json["translation_creation_time"]

    say("list my items")
    exp_list_fields = [
        "archived",
        "author",
        "descriptor_creation_time",
        "icon",
        "mine",
        "name",
        "ooni_run_link_id",
        "short_description",
        "translation_creation_time",
    ]
    r = usersession.get("/api/_/ooni_run/list")
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert sorted(r.json) == ["descriptors", "v"]
    assert len(r.json["descriptors"]) > 0
    assert sorted(r.json["descriptors"][0]) == exp_list_fields
    found = [d for d in r.json["descriptors"] if d["ooni_run_link_id"] == ooni_run_link_id]
    assert len(found) == 1

    say("list all items as admin")
    r = adminsession.get("/api/_/ooni_run/list")
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert sorted(r.json) == ["descriptors", "v"]
    assert len(r.json["descriptors"]) > 0
    assert sorted(r.json["descriptors"][0]) == exp_list_fields
    found = [d for d in r.json["descriptors"] if d["ooni_run_link_id"] == ooni_run_link_id]
    assert len(found) == 1

    ##  find the item created by usersession above
    # fixme
    # assert desc[0]["name_intl"] == "integ-test"

    say("list all items as anonymous")
    r = client.get("/api/_/ooni_run/list")
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert sorted(r.json) == ["descriptors", "v"]
    assert len(r.json["descriptors"]) > 0
    assert sorted(r.json["descriptors"][0]) == exp_list_fields
    say("find the item created by usersession above")
    desc = [d for d in r.json["descriptors"] if d["ooni_run_link_id"] == ooni_run_link_id][0]
    assert desc == {
        "archived": False,
        "author": "integ-test author",
        "descriptor_creation_time": creation_time,
        "icon": "myicon",
        "ooni_run_link_id": ooni_run_link_id,
        "mine": False,
        "name": "integ-test name in English",
        "short_description": "integ-test short description in English",
        "translation_creation_time": translation_creation_time,
    }

    ### "update" the oonirun by creating a new version, changing the inputs
    z["nettests"][0]["inputs"].append("https://foo.net/")
    exp["nettests"][0]["inputs"].append("https://foo.net/")
    r = usersession.post(f"/api/_/ooni_run/create?ooni_run_link_id={ooni_run_link_id}", json=z)
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert r.json["ooni_run_link_id"] == ooni_run_link_id

    say("Fetch it back")
    r = usersession.get(f"/api/_/ooni_run/fetch/{ooni_run_link_id}")
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert r.json["mine"] is True, r.json
    assert r.json["archived"] is False, r.json
    say("descriptor_creation_time has changed")
    assert creation_time < r.json["descriptor_creation_time"]
    assert translation_creation_time < r.json["translation_creation_time"]

    creation_time = r.json["descriptor_creation_time"]
    translation_creation_time = r.json["translation_creation_time"]

    say("List descriptors as admin and find we have 2 versions now")
    r = adminsession.get(f"/api/_/ooni_run/list?ids={ooni_run_link_id}")
    assert r.status_code == 200, r.json
    descs = r.json["descriptors"]
    assert len(descs) == 2, r.json

    say("List descriptors using more params")
    r = usersession.get(f"/api/_/ooni_run/list?ids={ooni_run_link_id}&only_mine=True")
    assert r.status_code == 200, r.json
    descs = r.json["descriptors"]
    assert len(descs) == 2, r.json
    for d in descs:
        assert d["mine"] is True
        assert d["archived"] is False

    say("Fail to update the oonirun using the wrong account")
    r = adminsession.post(f"/api/_/ooni_run/create?ooni_run_link_id={ooni_run_link_id}", json=z)
    assert r.status_code == 400, r.json
    assert r.json == {"error": "OONIRun descriptor not found"}

    say("# Update translations without changing descriptor_creation_time")
    z["description_intl"]["it"] = "integ-test *nuova* descrizione in italiano"
    r = usersession.post(f"/api/_/ooni_run/create?ooni_run_link_id={ooni_run_link_id}", json=z)
    assert r.status_code == 200, r.json
    say("previous id and descriptor_creation_time, not changed")
    assert r.json["ooni_run_link_id"] == ooni_run_link_id
    # assert creation_time == r.json["descriptor_creation_time"]

    say("Fetch latest and find descriptor_creation_time has not changed")
    r = usersession.get(f"/api/_/ooni_run/fetch/{ooni_run_link_id}")
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json
    assert sorted(r.json) == exp_fetch_fields
    say("Only the translation_creation_time increased")
    assert creation_time == r.json["descriptor_creation_time"]
    assert translation_creation_time < r.json["translation_creation_time"]
    exp["description_intl"]["it"] = "integ-test *nuova* descrizione in italiano"
    assert r.json["descriptor"] == exp
    assert r.json["mine"] is True, r.json
    assert r.json["archived"] is False, r.json

    say("Archive it")
    r = usersession.post(f"/api/_/ooni_run/archive/{ooni_run_link_id}")
    assert r.status_code == 200, r.json
    assert r.json["v"] == 1, r.json

    say("List descriptors")
    r = usersession.get(f"/api/_/ooni_run/list?ids={ooni_run_link_id}&include_archived=True")
    assert r.status_code == 200, r.json
    descs = r.json["descriptors"]
    assert len(descs) == 2, r.json

    say("List descriptors")
    r = usersession.get(f"/api/_/ooni_run/list?ids={ooni_run_link_id}")
    assert r.status_code == 200, r.json
    descs = r.json["descriptors"]
    assert len(descs) == 0, r.json

    say("Fetch latest and find that it's archived")
    r = usersession.get(f"/api/_/ooni_run/fetch/{ooni_run_link_id}")
    assert r.status_code == 200, r.json
    assert r.json["archived"] == True, r.json


def test_fetch_not_found(cleanup, usersession):
    r = usersession.get("/api/_/ooni_run/fetch/999999999999999")
    assert r.status_code == 400, r.json
    assert r.json == {"error": "oonirun descriptor not found"}
