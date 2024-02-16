"""
Integration test for OONIRn API
"""


def test_oonirun_create_and_fetch(
    client, client_with_user_role, client_with_admin_role
):
    say = print
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
    r = client_with_user_role.post("/api/v2/oonirun", json=z)
    assert r.status_code == 422, r.json()

    say("Empty name_intl->it")
    z["name"] = "integ-test name in English"
    r = client_with_user_role.post("/api/v2/oonirun", json=z)
    assert r.status_code == 422, r.json()

    ### Create descriptor as user
    z["name_intl"]["it"] = "integ-test nome in italiano"
    r = client_with_user_role.post("/api/v2/oonirun", json=z)
    print(r.json())
    assert r.status_code == 200, r.json()
    assert r.json()["v"] == 1, r.json()
    assert str(r.json()["oonirun_link_id"]).endswith("00")
    ooni_run_link_id = int(r.json()["oonirun_link_id"])

    say("fetch latest")
    r = client_with_user_role.get(f"/api/v2/oonirun/{ooni_run_link_id}")
    assert r.status_code == 200, r.json()
    assert r.json()["v"] == 1, r.json()
    exp_fetch_fields = [
        "nettests",
        "date_created",
        "date_updated",
        "is_archived",
        "is_mine",
        "name",
        "v",
    ]
    missing_keys = set(exp_fetch_fields) - set(r.json().keys())
    assert len(missing_keys) == 0
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
        "is_archived": False,
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
    j = r.json()
    for k, v in exp.items():
        assert j[k] == v, f"{k} {j[k]}!= {v}"

    creation_time = r.json()["date_created"]
    revision = r.json()["revision"]
    assert creation_time.endswith("Z")

    say = print
    say("fetch by creation_time")
    r = client_with_user_role.get(
        f"/api/v2/oonirun/{ooni_run_link_id}?revision={revision}"
    )
    assert r.status_code == 200, r.json()
    assert r.json()["v"] == 1, r.json()
    missing_keys = set(exp_fetch_fields) - set(r.json().keys())
    assert len(missing_keys) == 0
    j = r.json()
    for k, v in exp.items():
        assert j[k] == v, f"{k} {j[k]}!= {v}"
    assert creation_time == r.json()["date_created"]
    assert revision == r.json()["revision"]

    say("list my items")
    exp_list_fields = [
        "author",
        "date_updated",
        "icon",
        "is_archived",
        "is_mine",
        "name",
        "oonirun_link_id",
        "short_description",
        "date_created",
    ]
    r = client_with_user_role.get("/api/v2/oonirun/")
    assert r.status_code == 200, r.json()
    assert r.json()["v"] == 1, r.json()
    assert sorted(r.json()) == ["descriptors", "v"]
    assert len(r.json()["descriptors"]) > 0
    missing_keys = set(exp_list_fields) - set(r.json()["descriptors"][0].keys())
    assert len(missing_keys) == 0
    found = [
        d for d in r.json()["descriptors"] if d["oonirun_link_id"] == ooni_run_link_id
    ]
    assert len(found) == 1

    say("list all items as admin")
    r = client_with_admin_role.get("/api/v2/oonirun/")
    assert r.status_code == 200, r.json()
    assert r.json()["v"] == 1, r.json()
    assert sorted(r.json()) == ["descriptors", "v"]
    assert len(r.json()["descriptors"]) > 0
    missing_keys = set(exp_list_fields) - set(r.json()["descriptors"][0].keys())
    assert len(missing_keys) == 0
    found = [
        d for d in r.json()["descriptors"] if d["oonirun_link_id"] == ooni_run_link_id
    ]
    assert len(found) == 1

    ##  find the item created by client_with_user_role above
    # fixme
    # assert desc[0]["name_intl"] == "integ-test"

    say("list all items as anonymous")
    r = client.get("/api/v2/oonirun/")
    assert r.status_code == 200, r.json()
    assert r.json()["v"] == 1, r.json()
    assert sorted(r.json()) == ["descriptors", "v"]
    assert len(r.json()["descriptors"]) > 0
    missing_keys = set(exp_list_fields) - set(r.json()["descriptors"][0].keys())
    assert len(missing_keys) == 0
    say("find the item created by client_with_user_role above")
    desc = [
        d for d in r.json()["descriptors"] if d["oonirun_link_id"] == ooni_run_link_id
    ][0]
    exp_desc = {
        "author": "integ-test author",
        "date_created": creation_time,
        "icon": "myicon",
        "oonirun_link_id": ooni_run_link_id,
        "is_archived": False,
        "is_mine": False,
        "name": "integ-test name in English",
        "short_description": "integ-test short description in English",
    }
    for k, v in exp_desc.items():
        assert desc[k] == v, f"{k} {j[k]}!= {v}"

    ### "update" the oonirun by creating a new version, changing the inputs
    z["nettests"][0]["inputs"].append("https://foo.net/")
    exp["nettests"][0]["inputs"].append("https://foo.net/")
    r = client_with_user_role.put(f"/api/v2/oonirun/{ooni_run_link_id}", json=z)
    assert r.status_code == 200, r.json()
    assert r.json()["v"] == 1, r.json()
    assert r.json()["oonirun_link_id"] == ooni_run_link_id

    say("Fetch it back")
    r = client_with_user_role.get(f"/api/v2/oonirun/{ooni_run_link_id}")
    assert r.status_code == 200, r.json()
    assert r.json()["v"] == 1, r.json()
    assert r.json()["is_mine"] is True, r.json()
    assert r.json()["is_archived"] is False, r.json()
    say("revision has changed")
    print(r.json())
    assert revision < r.json()["revision"]

    creation_time = r.json()["date_created"]

    say("List descriptors as admin and find we have 2 versions now")
    r = client_with_admin_role.get(f"/api/v2/oonirun/?ids={ooni_run_link_id}")
    assert r.status_code == 200, r.json()
    descs = r.json()["descriptors"]
    assert len(descs) == 2, r.json()

    say("List descriptors using more params")
    r = client_with_user_role.get(
        f"/api/v2/oonirun/?ids={ooni_run_link_id}&only_mine=True"
    )
    assert r.status_code == 200, r.json()
    descs = r.json()["descriptors"]
    assert len(descs) == 2, r.json()
    for d in descs:
        assert d["is_mine"] is True
        assert d["is_archived"] is False

    # XXX this is wrong. Admin can do everything.
    # TODO(art): add test for trying to edit from a non-admin account
    # say("Fail to update the oonirun using the wrong account")
    # r = client_with_admin_role.put(f"/api/v2/oonirun/{ooni_run_link_id}", json=z)
    # assert r.status_code == 400, r.json()
    # assert r.json() == {"error": "OONIRun descriptor not found"}

    say("# Update translations without changing descriptor_creation_time")
    z["description_intl"]["it"] = "integ-test *nuova* descrizione in italiano"
    r = client_with_user_role.put(f"/api/v2/oonirun/{ooni_run_link_id}", json=z)
    assert r.status_code == 200, r.json()
    say("previous id and descriptor_creation_time, not changed")
    assert r.json()["oonirun_link_id"] == ooni_run_link_id
    # assert creation_time == r.json()["descriptor_creation_time"]

    say("Fetch latest and find descriptor_creation_time has not changed")
    r = client_with_user_role.get(f"/api/v2/oonirun/{ooni_run_link_id}")
    assert r.status_code == 200, r.json()
    assert r.json()["v"] == 1, r.json()
    missing_keys = set(exp_fetch_fields) - set(r.json().keys())
    assert len(missing_keys) == 0
    say("Only the translation_creation_time increased")
    assert creation_time == r.json()["date_updated"]
    exp["description_intl"]["it"] = "integ-test *nuova* descrizione in italiano"
    j = r.json()
    for k, v in exp.items():
        assert j[k] == v, f"{k} {j[k]}!= {v}"
    assert r.json()["is_mine"] is True, r.json()
    assert r.json()["is_archived"] is False, r.json()

    # TODO(art): this test needs to be more correct
    # say("Archive it")
    # r = client_with_user_role.put(f"/api/v2/oonirun/{ooni_run_link_id}")
    # assert r.status_code == 200, r.json()
    # assert r.json()["v"] == 1, r.json()

    # say("List descriptors")
    # r = client_with_user_role.get(
    #    f"/api/v2/oonirun/?ids={ooni_run_link_id}&include_archived=True"
    # )
    # assert r.status_code == 200, r.json()
    # descs = r.json()["descriptors"]
    # assert len(descs) == 2, r.json()

    # say("List descriptors")
    # r = client_with_user_role.get(f"/api/v2/oonirun/?ids={ooni_run_link_id}")
    # assert r.status_code == 200, r.json()
    # descs = r.json()["descriptors"]
    # assert len(descs) == 0, r.json()

    # say("Fetch latest and find that it's archived")
    # r = client_with_user_role.get(f"/api/v2/oonirun/{ooni_run_link_id}")
    # assert r.status_code == 200, r.json()
    # assert r.json()["is_archived"] == True, r.json()


def test_fetch_not_found(client_with_user_role):
    r = client_with_user_role.get("/api/_/ooni_run/fetch/999999999999999")
    assert r.status_code == 404, r.json()
    assert "not found" in r.json()["detail"].lower()
