"""
Integration test for Citizenlab API

Warning: this test runs against GitHub and opens PRs

Warning: writes git repos on disk

Lint using Black.

Test using:
    hatch run test
"""

import pytest

# debdeps: python3-pytest-mock

import citizenlab.manager


def test_no_auth(client):
    r = client.get("/api/_/url-submission/test-list/global")
    assert r.status_code == 401


def list_global(client_with_user_role):
    r = client_with_user_role.get("/api/_/url-submission/test-list/global")
    assert r.status_code == 200
    tl = r.json()["test_list"]
    assert tl[0].keys() == {"url", "category_code", "date_added", "source", "notes"}
    assert len(tl) > 1000
    return r.json()


def test_list_unsupported_country(client_with_user_role):
    r = client_with_user_role.get("/api/_/url-submission/test-list/XY")
    assert r.status_code == 200
    assert r.json()["test_list"] == None


def add_url(client_with_user_role, url, tmp_path):
    new_entry = {
        "url": url,
        "category_code": "FILE",
        "date_added": "2017-04-12",
        "source": "",
        "notes": "Integ test",
    }
    d = dict(
        country_code="US",
        new_entry=new_entry,
        #old_entry={}, # XXX empty dict fails validation for missing required fields 
        comment="Integ test: add example URL",
    )

    r = client_with_user_role.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.content

    r = client_with_user_role.get("/api/_/url-submission/test-list/us")
    assert r.status_code == 200
    tl = r.json()["test_list"]
    en = [e for e in tl if e["url"] == url]
    assert len(en) == 1
    assert en[0] == new_entry


def lookup_and_delete_us_url(client_with_user_role, url):
    r = client_with_user_role.get("/api/_/url-submission/test-list/us")
    assert r.status_code == 200
    tl = r.json()["test_list"]
    en = [e for e in tl if e["url"] == url]
    assert len(en) == 1
    old_entry = en[0]
    assert sorted(old_entry) == [
        "category_code",
        "date_added",
        "notes",
        "source",
        "url",
    ]
    d = dict(
        country_code="US",
        #new_entry={}, #XXX empty dict fails validation for missing required fields
        old_entry=old_entry,
        comment="Integ test: delete URL",
    )

    r = client_with_user_role.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.content


def test_update_url_reject(client_with_user_role):
    d = dict(
        country_code="it",
        old_entry={
            "url": "http://btdigg.org/",
            "category_code": "FILE",
            "date_added": "2017-04-12",
            "source": "",
            "notes": "<bogus value not matching anything>",
        },
        new_entry={
            "url": "https://btdigg.org/",
            "category_code": "FILE",
            "date_added": "2017-04-12",
            "source": "",
            "notes": "Meow",
        },
        comment="add HTTPS to the website url",
    )
    r = client_with_user_role.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 400, r.json()


def test_update_url_nochange(client, client_with_user_role):
    r = client_with_user_role.get("/api/_/url-submission/test-list/it")
    assert r.status_code == 200
    tl = r.json()["test_list"]

    fe = tl[0]  # first entry
    old = {
        "url": fe["url"],
        "category_code": fe["category_code"],
        "date_added": fe["date_added"],
        "source": fe["source"],
        "notes": fe["notes"],
    }
    new = old
    d = dict(country_code="it", old_entry=old, new_entry=new, comment="")
    r = client_with_user_role.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 400
    assert b"err_no_proposed_changes" in r.content


# TODO reset git
# TODO open PR
def update_url_basic(client_with_user_role):
    r = client_with_user_role.get("/api/_/url-submission/test-list/it")
    assert r.status_code == 200
    tl = r.json()["test_list"]

    fe = tl[0]  # first entry
    old = {
        "url": fe["url"],
        "category_code": fe["category_code"],
        "date_added": fe["date_added"],
        "source": fe["source"],
        "notes": fe["notes"],
    }
    new = old.copy()
    new["notes"] = "Bogus comment"
    assert new != old
    d = dict(country_code="it", old_entry=old, new_entry=new, comment="")
    r = client_with_user_role.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.content

    assert get_state(client_with_user_role) == "IN_PROGRESS"


def delete_url(client_with_user_role):
    d = dict(
        country_code="US",
        old_entry={
            "url": "https://www.example.com/",
            "category_code": "FILE",
            "date_added": "2017-04-12",
            "source": "",
            "notes": "",
        },
        #old_entry={}, # XXX empty dict fails validation for missing required fields 
        comment="delete example URL",
    )

    r = client_with_user_role.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.content


def get_state(client_with_user_role, cc="ie"):
    # state is independent from cc
    r = client_with_user_role.get(f"/api/_/url-submission/test-list/{cc}")
    assert r.status_code == 200
    return r.json()["state"]


def test_pr_state(client_with_user_role):
    assert get_state(client_with_user_role) == "CLEAN"


# # Tests with mocked-out GitHub # #


class MKOpen:
    status_code = 200

    @staticmethod
    def json():  # mock both openin a pr or checking its status
        return {"state": "open", "url": "https://testurl"}


class MKClosed:
    status_code = 200

    @staticmethod
    def json():  # mock both openin a pr or checking its status
        return {"state": "closed", "url": "https://testurl"}


@pytest.fixture
def mock_requests_open(monkeypatch):
    def req(*a, **kw):
        print(a)
        print(kw)
        return MKOpen()

    def push(*a, **kw):
        print(a)
        print(kw)
        return MKOpen()

    monkeypatch.setattr(citizenlab.manager.URLListManager, "_push_to_repo", push)
    monkeypatch.setattr(citizenlab.manager.requests, "post", req)
    monkeypatch.setattr(citizenlab.manager.requests, "patch", req)
    monkeypatch.setattr(citizenlab.manager.requests, "get", req)


@pytest.fixture
def mock_requests_closed(monkeypatch):
    def req(*a, **kw):
        print(a)
        print(kw)
        return MKClosed()

    def push(*a, **kw):
        print(a)
        print(kw)
        return MKClosed()

    monkeypatch.setattr(citizenlab.manager.URLListManager, "_push_to_repo", push)
    monkeypatch.setattr(citizenlab.manager.requests, "post", req)
    monkeypatch.setattr(citizenlab.manager.requests, "patch", req)
    monkeypatch.setattr(citizenlab.manager.requests, "get", req)


def _read_us_csv_file(tmp_path):
    # read from user repo path: citizenlab.py get_user_repo_path
    account_id = "0" * 16
    f = tmp_path / "users" / account_id / "test-lists/lists/us.csv"
    return f.read_text().splitlines()


def _test_checkout_update_submit(client_with_user_role, tmp_path):
    assert get_state(client_with_user_role) == "CLEAN"

    r = list_global(client_with_user_role)
    assert r["state"] == "CLEAN"

    url = "https://example-bogus-1.org/"
    add_url(client_with_user_role, url, tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    csv = _read_us_csv_file(tmp_path)
    assert csv[0] == "url,category_code,category_description,date_added,source,notes"
    assert url in csv[-1], "URL not found in the last line in the CSV file"

    r = client_with_user_role.get("/api/_/url-submission/test-list/us")
    assert r.status_code == 200

    assert len(r.json()["changes"]["us"]) == 1

    add_url(client_with_user_role, "https://example-bogus.org/", tmp_path)
    lookup_and_delete_us_url(client_with_user_role, "https://example-bogus.org/")

    update_url_basic(client_with_user_role)

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200

    # This is clean, because we are mocking the is_pr_resolved request, making
    # the test client believe that the PR has been merged.
    assert get_state(client_with_user_role) == "CLEAN"

    r = client_with_user_role.get("/api/_/url-submission/test-list/us")
    assert r.json()["changes"] == {}


def test_checkout_update_submit(
    client, client_with_user_role, mock_requests_closed, tmp_path
):
    _test_checkout_update_submit(client_with_user_role, tmp_path)

    # Before getting the list URLListManager will check if the mock PR is done
    # (it is) and set the state to CLEAN
    r = list_global(client_with_user_role)
    assert r["state"] == "CLEAN"


def test_propose_changes_then_update(
    client_with_user_role, mock_requests_open, tmp_path
):
    assert get_state(client_with_user_role) == "CLEAN"

    url = "https://example-bogus-1.org/"
    add_url(client_with_user_role, url, tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200

    assert get_state(client_with_user_role) == "PR_OPEN"

    url = "https://example-bogus-2.org/"
    add_url(client_with_user_role, url, tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200

    assert get_state(client_with_user_role) == "PR_OPEN"


# # Tests with real GitHub # #


@pytest.mark.skipif(not pytest.run_ghpr, reason="use --ghpr to run")
def test_ghpr_checkout_update_submit(client_with_user_role, tmp_path):
    _test_checkout_update_submit(client_with_user_role, tmp_path)
    # This is a *real* PR
    r = list_global(client_with_user_role)
    assert r["state"] == "PR_OPEN"


# # Prioritization management # #


def test_url_priorities_crud(client_with_admin_role, url_prio_tblready):
    adminsession = client_with_admin_role
    def match(url):
        # count how many times `url` appears in the list
        exp = {
            "category_code": "NEWS",
            "cc": "*",
            "domain": "*",
            "priority": 100,
            "url": url,
        }
        r = adminsession.get("/api/_/url-priorities/list")
        assert r.status_code == 200, r.json()
        for x in r.json()["rules"]:
            for k, v in x.items():
                assert v != '', f"Empty value in {x}"
        match = [x for x in r.json()["rules"] if x == exp]
        return len(match)

    assert match("INTEG-TEST") == 0
    assert match("INTEG-TEST2") == 0

    r = adminsession.get("/api/_/url-priorities/list")
    assert r.status_code == 200, r.json()
    assert len(r.json()["rules"]) > 20

    d = dict()
    r = adminsession.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 400, r.json()

    # Create
    xxx = dict(category_code="NEWS", priority=100, cc='', url="INTEG-TEST")
    d = dict(new_entry=xxx)
    r = adminsession.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 200, r.json()

    # Ensure the new entry is present
    assert match("INTEG-TEST") == 1

    # Fail to create a duplicate
    d = dict(new_entry=xxx)
    r = adminsession.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 400, r.json()

    # Update (change URL)
    yyy = dict(category_code="NEWS", priority=100, url="INTEG-TEST2")
    d = dict(old_entry=xxx, new_entry=yyy)
    r = adminsession.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 200, r.json()
    assert match("INTEG-TEST") == 0
    assert match("INTEG-TEST2") == 1

    # Delete
    d = dict(old_entry=yyy)
    r = adminsession.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 200, r.json()
    assert r.json == 1

    assert match("INTEG-TEST") == 0
    assert match("INTEG-TEST2") == 0


def post(client, url, **kw):
    return client.post(url, json=kw)


def post200(client, url, **kw):
    r = post(client, url, **kw)
    assert r.status_code == 200, r.json()
    return r


def test_x(client_with_admin_role):
    adminsession = client_with_admin_role
    xxx = dict(category_code="NEWS", priority=10, cc="it")
    yyy = dict(category_code="NEWS", priority=5, domain="www.leggo.it")
    zzz = dict(cc="it", priority=3, url="http://www.leggo.it/")

    post(adminsession, "/api/_/url-priorities/update", old_entry=xxx)
    post(adminsession, "/api/_/url-priorities/update", old_entry=yyy)
    post(adminsession, "/api/_/url-priorities/update", old_entry=zzz)

    post200(adminsession, "/api/_/url-priorities/update", new_entry=xxx)
    post200(adminsession, "/api/_/url-priorities/update", new_entry=yyy)
    post200(adminsession, "/api/_/url-priorities/update", new_entry=zzz)

    ## XXX currently broken
    # r = client.get("/api/_/url-priorities/WIP")
    # assert r.json
    # for e in r.json:
    #    if e["category_code"] == "NEWS" and e["cc"] == "it" and e["url"] == 'http://www.leggo.it/':
    #        assert e["priority"] == 118  # 4 rules matched

    post200(adminsession, "/api/_/url-priorities/update", old_entry=xxx)
    post200(adminsession, "/api/_/url-priorities/update", old_entry=yyy)
    post200(adminsession, "/api/_/url-priorities/update", old_entry=zzz)
