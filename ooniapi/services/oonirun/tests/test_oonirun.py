"""
Integration test for OONIRn API
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import time

from oonirun import models
from oonirun.routers.v2 import utcnow_seconds
import pytest

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

SAMPLE_OONIRUN = {
    "name": "",
    "name_intl": {},
    "description": "integ-test description in English",
    "description_intl": {
        "es": "integ-test descripción en español",
    },
    "short_description": "integ-test short description in English",
    "short_description_intl": {
        "it": "integ-test descrizione breve in italiano",
    },
    "icon": "myicon",
    "author": "oonitarian@example.com",
    "nettests": [
        {
            "inputs": [
                "https://example.com/",
                "https://ooni.org/",
            ],
            "options": {
                "HTTP3Enabled": True,
            },
            "backend_options": {},
            "is_background_run_enabled_default": False,
            "is_manual_run_enabled_default": False,
            "test_name": "web_connectivity",
        },
        {
            "inputs": [],
            "options": {},
            "backend_options": {},
            "is_background_run_enabled_default": False,
            "is_manual_run_enabled_default": False,
            "test_name": "dnscheck",
        },
    ],
}

EXPECTED_OONIRUN_LINK_PUBLIC_KEYS = [
    "oonirun_link_id",
    "date_created",
    "date_updated",
    "revision",
    "is_mine",
    "is_expired",
    "name",
    "short_description",
    "description",
    "author",
    "nettests",
    "name_intl",
    "short_description_intl",
    "description_intl",
    "icon",
    "color",
    "expiration_date",
]


def test_get_version(client):
    r = client.get("/version")
    j = r.json()
    assert "version" in j
    assert "build_label" in j


def test_get_root(client):
    r = client.get("/")
    assert r.status_code == 200


def test_oonirun_author_validation(client, client_with_user_role):
    z = deepcopy(SAMPLE_OONIRUN)
    z["name"] = "integ-test name in English"
    del z["author"]
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 422, "empty author should be rejected"

    z["author"] = "not an author"
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code != 200, "invalid author is rejected"

    z["author"] = "nome@example.com"
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code != 200, "invalid author is rejected"

    z["author"] = "oonitarian@example.com"
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 200, "valid author is OK"


def test_oonirun_validation(client, client_with_user_role):
    z = deepcopy(SAMPLE_OONIRUN)
    r = client.post("/api/v2/oonirun/links", json=z)
    assert r.status_code != 200, "unauthenticated requests are rejected"

    z = deepcopy(SAMPLE_OONIRUN)
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 422, "empty name should be rejected"

    z["name"] = "integ-test name in English"
    z["name_intl"] = {"it": ""}
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 422, "empty name_intl should be rejected"

    z = deepcopy(SAMPLE_OONIRUN)
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 422, "empty name should be rejected"

    z["name"] = "integ-test name in English"
    z["name_intl"] = None
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 200, "name_intl can be None"


def test_oonirun_not_found(client, client_with_user_role):
    z = deepcopy(SAMPLE_OONIRUN)
    ### Create descriptor as user
    z["name"] = "integ-test name in English"
    z["name_intl"]["it"] = "integ-test nome in italiano"
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 200, r.json()
    j = r.json()
    assert str(j["oonirun_link_id"]).startswith("10")
    oonirun_link_id = r.json()["oonirun_link_id"]

    # try to change the email to a different value
    j["author"] = "notme@example.com"
    r = client_with_user_role.put(f"/api/v2/oonirun/links/{oonirun_link_id}", json=j)
    assert r.status_code != 200, r.json()

    # Expire the link
    j["author"] = "oonitarian@example.com"
    j["expiration_date"] = (utcnow_seconds() + timedelta(minutes=-1)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    r = client_with_user_role.put(f"/api/v2/oonirun/links/{oonirun_link_id}", json=j)
    assert r.status_code == 200, r.json()

    not_existing_link_id = "1234676871672836187"
    r = client_with_user_role.put(
        f"/api/v2/oonirun/links/{not_existing_link_id}", json=j
    )
    assert r.status_code == 404, r.json()

    r = client.get(f"/api/v2/oonirun/links/{not_existing_link_id}")
    assert r.status_code == 404, r.json()

    r = client_with_user_role.put(f"/api/v2/oonirun/links/{oonirun_link_id}", json=j)
    assert r.status_code == 403, "expired link cannot be edited"

    r = client_with_user_role.get(f"/api/v2/oonirun/links")
    j = r.json()
    assert r.status_code == 200, r.json()
    assert j["oonirun_links"] == []


def test_oonirun_admin(client_with_user_role, client_with_admin_role):
    z = deepcopy(SAMPLE_OONIRUN)
    ### Create link as user
    z["name"] = "integ-test name in English"
    z["name_intl"]["it"] = "integ-test nome in italiano"
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 200, r.json()
    assert str(r.json()["oonirun_link_id"]).startswith("10")
    oonirun_link_id = r.json()["oonirun_link_id"]

    r = client_with_user_role.put("/api/v2/oonirun/links", json=z)
    z["name"] = "changed name by user"
    r = client_with_user_role.put(f"/api/v2/oonirun/links/{oonirun_link_id}", json=z)
    assert r.status_code == 200, r.json()

    z["name"] = "changed name by admin"
    r = client_with_admin_role.put(f"/api/v2/oonirun/links/{oonirun_link_id}", json=z)
    assert r.status_code == 200, r.json()


def test_oonirun_full_workflow(client, client_with_user_role, client_with_admin_role):
    z = deepcopy(SAMPLE_OONIRUN)
    ### Create 2 descriptors as user
    z["name"] = "integ-test name in English"
    z["name_intl"]["it"] = "integ-test nome in italiano"
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 200, r.json()
    assert str(r.json()["oonirun_link_id"]).startswith("10")
    oonirun_link_id = r.json()["oonirun_link_id"]

    z["name"] = "second descriptor in English"
    z["name_intl"]["it"] = "second integ-test nome in italiano"
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 200, r.json()
    assert str(r.json()["oonirun_link_id"]).startswith("10")
    oonirun_link_id = r.json()["oonirun_link_id"]

    r = client_with_user_role.get(f"/api/v2/oonirun/links/{oonirun_link_id}")
    assert r.status_code == 200, r.json()

    j = r.json()
    assert j["name"] == z["name"]
    assert j["name_intl"] == z["name_intl"]
    assert j["description"] == z["description"]
    assert j["nettests"] == z["nettests"]
    date_created = datetime.strptime(
        j["date_created"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    assert date_created < utcnow_seconds() + timedelta(minutes=+10)
    assert date_created > utcnow_seconds() + timedelta(hours=-1)

    date_updated = datetime.strptime(
        j["date_updated"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    assert date_updated < utcnow_seconds() + timedelta(minutes=+10)
    assert date_updated > utcnow_seconds() + timedelta(hours=-1)

    assert j["is_mine"] == True
    assert j["revision"] == "1"

    ## Fetch by revision
    r = client_with_user_role.get(f"/api/v2/oonirun/links/{oonirun_link_id}?revision=1")
    assert r.status_code == 200, r.json()

    j = r.json()
    assert j["name"] == z["name"]
    assert j["name_intl"] == z["name_intl"]
    assert j["author"] == z["author"]
    assert j["description"] == z["description"]
    assert j["nettests"] == z["nettests"]

    date_created = datetime.strptime(
        j["date_created"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    assert date_created < utcnow_seconds() + timedelta(minutes=10)
    assert date_created > utcnow_seconds() + timedelta(hours=-1)

    date_updated = datetime.strptime(
        j["date_updated"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    assert date_updated < utcnow_seconds() + timedelta(minutes=+10)
    assert date_updated > utcnow_seconds() + timedelta(hours=-1)

    assert j["is_mine"] == True
    assert j["revision"] == "1"

    r = client_with_user_role.get("/api/v2/oonirun/links")
    assert r.status_code == 200, r.json()

    j = r.json()
    assert len(j["oonirun_links"]) > 0

    found = False
    for d in j["oonirun_links"]:
        if d["oonirun_link_id"] == oonirun_link_id:
            found = True
        assert sorted(d.keys()) == sorted(EXPECTED_OONIRUN_LINK_PUBLIC_KEYS)
    assert found == True

    ## list all items as admin
    r = client_with_admin_role.get("/api/v2/oonirun/links")
    assert r.status_code == 200, r.json()

    j = r.json()
    assert len(j["oonirun_links"]) > 0

    found = False
    for d in j["oonirun_links"]:
        if d["oonirun_link_id"] == oonirun_link_id:
            found = True
        assert sorted(d.keys()) == sorted(EXPECTED_OONIRUN_LINK_PUBLIC_KEYS)
    assert found == True

    ##  find the item created by client_with_user_role above
    # fixme
    # assert desc[0]["name_intl"] == "integ-test"

    ## list all items as anonymous
    r = client.get("/api/v2/oonirun/links")
    assert r.status_code == 200, r.json()

    j = r.json()
    assert len(j["oonirun_links"]) > 0

    found = False
    for d in j["oonirun_links"]:
        if d["oonirun_link_id"] == oonirun_link_id:
            found = True
            assert d["is_mine"] == False
            assert d["is_expired"] == False

        assert sorted(d.keys()) == sorted(EXPECTED_OONIRUN_LINK_PUBLIC_KEYS)
    assert found == True

    ### "update" the oonirun by creating a new version, changing the inputs
    z["nettests"][0]["inputs"].append("https://foo.net/")
    r = client_with_user_role.put(f"/api/v2/oonirun/links/{oonirun_link_id}", json=z)
    assert r.status_code == 200, r.json()
    assert r.json()["oonirun_link_id"] == oonirun_link_id

    ## Fetch it back
    r = client_with_user_role.get(f"/api/v2/oonirun/links/{oonirun_link_id}")
    assert r.status_code == 200, r.json()

    j = r.json()
    assert j["is_mine"] is True, r.json()
    assert j["is_expired"] is False, r.json()
    assert int(j["revision"]) > 1, r.json()

    ## List descriptors as admin and find 2 of them
    r = client_with_admin_role.get(f"/api/v2/oonirun/links")
    assert r.status_code == 200, r.json()
    descs = r.json()["oonirun_links"]
    assert len(descs) == 2, r.json()

    ## List descriptors using more params
    r = client_with_user_role.get(f"/api/v2/oonirun/links?is_mine=True")
    assert r.status_code == 200, r.json()
    descs = r.json()["oonirun_links"]
    assert len(descs) == 2, r.json()
    for d in descs:
        assert d["is_mine"] is True
        assert d["is_expired"] is False

    # XXX this is wrong. Admin can do everything.
    # TODO(art): add test for trying to edit from a non-admin account
    # say("Fail to update the oonirun using the wrong account")
    # r = client_with_admin_role.put(f"/api/v2/oonirun/links/{ooni_run_link_id}", json=z)
    # assert r.status_code == 400, r.json()
    # assert r.json() == {"error": "OONIRun descriptor not found"}

    # Update translations without changing descriptor_creation_time

    # We need to pause 1 second for the update time to be different
    time.sleep(1)
    z["description_intl"]["it"] = "integ-test *nuova* descrizione in italiano"
    r = client_with_user_role.put(f"/api/v2/oonirun/links/{oonirun_link_id}", json=z)
    assert r.status_code == 200, r.json()

    ## previous id and descriptor_creation_time, not changed
    assert r.json()["oonirun_link_id"] == oonirun_link_id
    # assert creation_time == r.json()["descriptor_creation_time"]

    ## Fetch latest and find descriptor_creation_time has not changed
    r = client_with_user_role.get(f"/api/v2/oonirun/links/{oonirun_link_id}")
    assert r.status_code == 200, r.json()

    j = r.json()

    assert sorted(j.keys()) == sorted(EXPECTED_OONIRUN_LINK_PUBLIC_KEYS)

    date_created = datetime.strptime(
        j["date_created"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    assert date_created < utcnow_seconds() + timedelta(minutes=30)
    assert date_created > utcnow_seconds() + timedelta(hours=-1)

    date_updated = datetime.strptime(
        j["date_updated"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    assert date_updated < utcnow_seconds() + timedelta(minutes=30)
    assert date_updated > utcnow_seconds() + timedelta(hours=-1)

    assert date_updated > date_created

    assert j["description_intl"]["it"] == "integ-test *nuova* descrizione in italiano"
    assert j["is_mine"] == True

    # Archive it
    edit_req = deepcopy(j)
    edit_req["expiration_date"] = (utcnow_seconds() + timedelta(minutes=-1)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    r = client_with_user_role.put(
        f"/api/v2/oonirun/links/{oonirun_link_id}", json=edit_req
    )
    j = r.json()
    assert r.status_code == 200, r.json()
    assert j["is_expired"] == True

    ## List descriptors after expiration
    r = client_with_user_role.get(f"/api/v2/oonirun/links?is_expired=True")
    j = r.json()
    assert r.status_code == 200, r.json()
    descs = j["oonirun_links"]
    assert len(descs) == 2, r.json()

    ## List descriptors filtered by ID
    r = client_with_user_role.get(f"/api/v2/oonirun/links/{oonirun_link_id}")
    assert r.status_code == 200, r.json()
    descs = r.json()["nettests"]
    assert len(descs) == 2, r.json()

    ## List descriptors
    r = client_with_user_role.get(f"/api/v2/oonirun/links")
    assert r.status_code == 200, r.json()
    descs = r.json()["oonirun_links"]
    assert len(descs) == 1, r.json()

    ## Fetch latest and find that it's archived
    r = client_with_user_role.get(f"/api/v2/oonirun/links/{oonirun_link_id}")
    assert r.status_code == 200, r.json()
    assert r.json()["is_expired"] == True, r.json()


def test_oonirun_expiration(client, client_with_user_role):
    z = deepcopy(SAMPLE_OONIRUN)
    ### Create descriptor as user
    z["name"] = "integ-test name in English"
    z["name_intl"]["it"] = "integ-test nome in italiano"
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 200, r.json()
    assert str(r.json()["oonirun_link_id"]).startswith("10")
    oonirun_link_id = r.json()["oonirun_link_id"]

    ## Fetch anonymously and check it's not expired
    r = client.get(f"/api/v2/oonirun/links/{oonirun_link_id}")
    j = r.json()
    assert r.status_code == 200, r.json()
    assert j["is_expired"] == False, r.json()

    ## Create new revision
    j["nettests"][0]["inputs"].append("https://foo.net/")
    r = client_with_user_role.put(f"/api/v2/oonirun/links/{oonirun_link_id}", json=j)
    assert r.status_code == 200, r.json()
    j = r.json()
    expiration_date = j["expiration_date"]

    ## Fetch anonymously and check it's got the new revision
    r = client.get(f"/api/v2/oonirun/links/{oonirun_link_id}")
    j = r.json()
    assert j["revision"] == "2", "revision did not change"
    assert j["expiration_date"] == expiration_date

    ## Update expiry time
    j["expiration_date"] = (utcnow_seconds() + timedelta(minutes=-1)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    r = client_with_user_role.put(f"/api/v2/oonirun/links/{oonirun_link_id}", json=j)
    assert r.status_code == 200, r.json()
    assert r.json()["is_expired"] == True, r.json()

    ## Fetch anonymously and check it's expired
    r = client.get(f"/api/v2/oonirun/links/{oonirun_link_id}")
    assert r.status_code == 200, r.json()
    assert r.json()["is_expired"] == True, r.json()

    ## List descriptors after expiration
    r = client_with_user_role.get(f"/api/v2/oonirun/links")
    j = r.json()
    assert r.status_code == 200, r.json()
    descs = j["oonirun_links"]
    assert len(descs) == 0, r.json()

    ## List descriptors after expiration
    r = client_with_user_role.get(f"/api/v2/oonirun/links?is_expired=True")
    j = r.json()
    assert r.status_code == 200, r.json()
    descs = j["oonirun_links"]
    assert len(descs) == 1, r.json()
    for d in descs:
        assert d["is_expired"] == True, "is_expired should be True"


def test_oonirun_revisions(client, client_with_user_role):
    z = deepcopy(SAMPLE_OONIRUN)
    ### Create descriptor as user
    z["name"] = "first descriptor"
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 200, r.json()
    j = r.json()
    oonirun_link_id_one = j["oonirun_link_id"]

    ## Create two new revisions
    j["nettests"][0]["inputs"].append("https://foo.net/")
    r = client_with_user_role.put(
        f"/api/v2/oonirun/links/{oonirun_link_id_one}", json=j
    )
    assert r.status_code == 200, r.json()
    j = r.json()
    first_date_created = j["date_created"]

    time.sleep(1.2)
    j["nettests"][0]["inputs"].append("https://foo2.net/")
    r = client_with_user_role.put(
        f"/api/v2/oonirun/links/{oonirun_link_id_one}", json=j
    )
    assert r.status_code == 200, r.json()
    j = r.json()
    second_date_created = j["date_created"]

    ## Fetch first revision
    r = client.get(f"/api/v2/oonirun/links/{oonirun_link_id_one}/full-descriptor/1")
    j = r.json()
    assert r.status_code == 200, r.json()
    assert j["date_created"] == first_date_created

    ## Fetch second revision
    r = client.get(f"/api/v2/oonirun/links/{oonirun_link_id_one}/full-descriptor/2")
    j = r.json()
    assert r.status_code == 200, r.json()
    assert j["date_created"] == second_date_created

    ### Create another descriptor as user
    z["name"] = "second descriptor"
    r = client_with_user_role.post("/api/v2/oonirun/links", json=z)
    assert r.status_code == 200, r.json()
    j = r.json()
    oonirun_link_id_two = j["oonirun_link_id"]

    ## Create new revision
    j["nettests"][0]["inputs"].append("https://foo.net/")
    r = client_with_user_role.put(
        f"/api/v2/oonirun/links/{oonirun_link_id_two}", json=j
    )
    assert r.status_code == 200, r.json()

    ## Fetch anonymously and check it's got the new revision
    r = client.get(f"/api/v2/oonirun/links/{oonirun_link_id_one}")
    j = r.json()
    assert j["revision"] == "3", "revision is 3"

    r = client_with_user_role.get(f"/api/v2/oonirun/links")
    j = r.json()
    assert r.status_code == 200, r.json()
    descs = j["oonirun_links"]
    assert len(descs) == 2, r.json()

    ## Fetch latest revision number
    r = client.get(
        f"/api/v2/oonirun/links/{oonirun_link_id_one}/full-descriptor/latest"
    )
    j = r.json()
    assert j["revision"] == "3", "revision is 3"
    lastest_nettests = j["nettests"]
    latest_date_created = j["date_created"]

    ## Fetch specific revision number
    r = client.get(f"/api/v2/oonirun/links/{oonirun_link_id_one}/full-descriptor/2")
    j = r.json()
    assert j["revision"] == "2", "revision is 2"

    ## Get revision list
    r = client.get(f"/api/v2/oonirun/links/{oonirun_link_id_one}/revisions")
    j = r.json()
    assert len(j["revisions"]) == 3, "there are 2 revisions"
    assert j["revisions"][0] == "3", "the latest one is 3"

    ## Fetch nettests for latest
    r = client.get(
        f"/api/v2/oonirun/links/{oonirun_link_id_one}/engine-descriptor/latest"
    )
    j_latest = r.json()
    assert j_latest["revision"] == "3", "revision is 3"
    assert j_latest["nettests"] == lastest_nettests, "nettests are the same"
    assert j_latest["date_created"] == latest_date_created, "date created matches"

    ## Should match latest
    r = client.get(f"/api/v2/oonirun/links/{oonirun_link_id_one}/engine-descriptor/3")
    assert j_latest == r.json()

    ## Fetch invalid revision number
    r = client.get(
        f"/api/v2/oonirun/links/{oonirun_link_id_one}/full-descriptor/notarevision"
    )
    j = r.json()
    assert r.status_code != 200, r.json()

    ## Get not-existing revision
    r = client.get(f"/api/v2/oonirun/links/404/revisions")
    j = r.json()
    assert r.status_code == 404, r.json()

    ## Get not-existing engine descriptor
    r = client.get(f"/api/v2/oonirun/links/404/engine-descriptor/latest")
    j = r.json()
    assert r.status_code == 404, r.json()
