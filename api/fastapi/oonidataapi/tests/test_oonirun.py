"""
Integration test for OONIRn API
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import time

SAMPLE_OONIRUN = {
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


def test_oonirun_validation(client, client_with_user_role, client_with_admin_role):
    z = deepcopy(SAMPLE_OONIRUN)
    r = client_with_user_role.post("/api/v2/oonirun", json=z)
    assert r.status_code == 422, "empty name should be rejected"

    z["name"] = "integ-test name in English"
    z["name_intl"] = {"it": ""}
    r = client_with_user_role.post("/api/v2/oonirun", json=z)
    assert r.status_code == 422, "empty name_intl should be rejected"


def test_oonirun_create_and_fetch(
    client, client_with_user_role, client_with_admin_role
):
    z = deepcopy(SAMPLE_OONIRUN)
    ### Create descriptor as user
    z["name"] = "integ-test name in English"
    z["name_intl"]["it"] = "integ-test nome in italiano"
    r = client_with_user_role.post("/api/v2/oonirun", json=z)
    print(r.json())
    assert r.status_code == 200, r.json()
    assert str(r.json()["oonirun_link_id"]).endswith("00")
    ooni_run_link_id = int(r.json()["oonirun_link_id"])

    r = client_with_user_role.get(f"/api/v2/oonirun/{ooni_run_link_id}")
    assert r.status_code == 200, r.json()

    j = r.json()
    assert j["name"] == z["name"]
    assert j["name_intl"] == z["name_intl"]
    assert j["description"] == z["description"]
    assert j["nettests"] == z["nettests"]
    date_created = datetime.strptime(
        j["date_created"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    assert date_created < datetime.now(timezone.utc)
    assert date_created > datetime.now(timezone.utc) + timedelta(hours=-1)

    date_updated = datetime.strptime(
        j["date_updated"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    assert date_updated < datetime.now(timezone.utc)
    assert date_updated > datetime.now(timezone.utc) + timedelta(hours=-1)

    assert j["is_mine"] == True
    assert j["revision"] == 1

    ## Fetch by revision
    r = client_with_user_role.get(f"/api/v2/oonirun/{ooni_run_link_id}?revision=1")
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
    assert date_created < datetime.now(timezone.utc)
    assert date_created > datetime.now(timezone.utc) + timedelta(hours=-1)

    date_updated = datetime.strptime(
        j["date_updated"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    assert date_updated < datetime.now(timezone.utc)
    assert date_updated > datetime.now(timezone.utc) + timedelta(hours=-1)

    assert j["is_mine"] == True
    assert j["revision"] == 1

    r = client_with_user_role.get("/api/v2/oonirun/")
    assert r.status_code == 200, r.json()

    j = r.json()
    assert len(j["descriptors"]) > 0

    found = False
    for d in j["descriptors"]:
        if d["oonirun_link_id"] == ooni_run_link_id:
            found = True
        assert sorted(d.keys()) == sorted(EXPECTED_OONIRUN_LINK_PUBLIC_KEYS)
    assert found == True

    ## list all items as admin
    r = client_with_admin_role.get("/api/v2/oonirun/")
    assert r.status_code == 200, r.json()

    j = r.json()
    assert len(j["descriptors"]) > 0

    found = False
    for d in j["descriptors"]:
        if d["oonirun_link_id"] == ooni_run_link_id:
            found = True
        assert sorted(d.keys()) == sorted(EXPECTED_OONIRUN_LINK_PUBLIC_KEYS)
    assert found == True

    ##  find the item created by client_with_user_role above
    # fixme
    # assert desc[0]["name_intl"] == "integ-test"

    ## list all items as anonymous
    r = client.get("/api/v2/oonirun/")
    assert r.status_code == 200, r.json()

    j = r.json()
    assert len(j["descriptors"]) > 0

    found = False
    for d in j["descriptors"]:
        if d["oonirun_link_id"] == ooni_run_link_id:
            found = True
            assert d["is_mine"] == False
            assert d["is_expired"] == False

        assert sorted(d.keys()) == sorted(EXPECTED_OONIRUN_LINK_PUBLIC_KEYS)
    assert found == True

    ### "update" the oonirun by creating a new version, changing the inputs
    z["nettests"][0]["inputs"].append("https://foo.net/")
    r = client_with_user_role.put(f"/api/v2/oonirun/{ooni_run_link_id}", json=z)
    assert r.status_code == 200, r.json()
    assert r.json()["oonirun_link_id"] == ooni_run_link_id

    ## Fetch it back
    r = client_with_user_role.get(f"/api/v2/oonirun/{ooni_run_link_id}")
    assert r.status_code == 200, r.json()

    j = r.json()
    assert j["is_mine"] is True, r.json()
    assert j["is_expired"] is False, r.json()
    assert j["revision"] > 1, r.json()

    ## List descriptors as admin and find we have 2 versions now
    r = client_with_admin_role.get(f"/api/v2/oonirun/?ids={ooni_run_link_id}")
    assert r.status_code == 200, r.json()
    descs = r.json()["descriptors"]
    assert len(descs) == 2, r.json()

    ## List descriptors using more params
    r = client_with_user_role.get(
        f"/api/v2/oonirun/?ids={ooni_run_link_id}&only_mine=True"
    )
    assert r.status_code == 200, r.json()
    descs = r.json()["descriptors"]
    assert len(descs) == 2, r.json()
    for d in descs:
        assert d["is_mine"] is True
        assert d["is_expired"] is False

    # XXX this is wrong. Admin can do everything.
    # TODO(art): add test for trying to edit from a non-admin account
    # say("Fail to update the oonirun using the wrong account")
    # r = client_with_admin_role.put(f"/api/v2/oonirun/{ooni_run_link_id}", json=z)
    # assert r.status_code == 400, r.json()
    # assert r.json() == {"error": "OONIRun descriptor not found"}

    # Update translations without changing descriptor_creation_time

    # We need to pause 1 second for the update time to be different
    time.sleep(1)
    z["description_intl"]["it"] = "integ-test *nuova* descrizione in italiano"
    r = client_with_user_role.put(f"/api/v2/oonirun/{ooni_run_link_id}", json=z)
    assert r.status_code == 200, r.json()

    ## previous id and descriptor_creation_time, not changed
    assert r.json()["oonirun_link_id"] == ooni_run_link_id
    # assert creation_time == r.json()["descriptor_creation_time"]

    ## Fetch latest and find descriptor_creation_time has not changed
    r = client_with_user_role.get(f"/api/v2/oonirun/{ooni_run_link_id}")
    assert r.status_code == 200, r.json()

    j = r.json()

    assert sorted(j.keys()) == sorted(EXPECTED_OONIRUN_LINK_PUBLIC_KEYS)

    date_created = datetime.strptime(
        j["date_created"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    assert date_created < datetime.now(timezone.utc)
    assert date_created > datetime.now(timezone.utc) + timedelta(hours=-1)

    date_updated = datetime.strptime(
        j["date_updated"], "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=timezone.utc)
    assert date_updated < datetime.now(timezone.utc)
    assert date_updated > datetime.now(timezone.utc) + timedelta(hours=-1)

    assert date_updated > date_created

    assert j["description_intl"]["it"] == "integ-test *nuova* descrizione in italiano"
    assert j["is_mine"] == True

    # Archive it
    edit_req = deepcopy(j)
    edit_req["expiration_date"] = (
        datetime.now(timezone.utc) + timedelta(minutes=-1)
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    r = client_with_user_role.put(f"/api/v2/oonirun/{ooni_run_link_id}", json=edit_req)
    j = r.json()
    assert r.status_code == 200, r.json()
    assert j["is_expired"] == True

    ## List descriptors after expiration
    r = client_with_user_role.get(
        f"/api/v2/oonirun/?ids={ooni_run_link_id}&include_expired=True"
    )
    j = r.json()
    print(j)
    assert r.status_code == 200, r.json()
    descs = j["descriptors"]
    assert len(descs) == 2, r.json()

    ## List descriptors
    r = client_with_user_role.get(f"/api/v2/oonirun/?ids={ooni_run_link_id}")
    assert r.status_code == 200, r.json()
    descs = r.json()["descriptors"]
    assert len(descs) == 0, r.json()

    ## "Fetch latest and find that it's archived
    r = client_with_user_role.get(f"/api/v2/oonirun/{ooni_run_link_id}")
    assert r.status_code == 200, r.json()
    assert r.json()["is_expired"] == True, r.json()


def test_fetch_not_found(client_with_user_role):
    r = client_with_user_role.get("/api/_/ooni_run/fetch/999999999999999")
    assert r.status_code == 404, r.json()
    assert "not found" in r.json()["detail"].lower()
