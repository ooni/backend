"""
Integration test for Citizenlab API

Warning: this test runs against GitHub and opens PRs

Warning: writes git repos on disk

Lint using Black.

Test using:
    pytest-3 -s --show-capture=no ooniapi/tests/integ/test_citizenlab.py
"""

import pytest

# debdeps: python3-pytest-mock

import ooniapi.citizenlab

from .test_integration_auth import _register_and_login
from .test_integration_auth import reset_smtp_mock, setup_test_session
from .test_integration_auth import adminsession, usersession
from tests.utils import *


def test_no_auth(client):
    r = client.get("/api/_/url-submission/test-list/global")
    assert r.status_code == 401


def list_global(usersession):
    r = usersession.get("/api/_/url-submission/test-list/global")
    assert r.status_code == 200
    tl = r.json["test_list"]
    assert tl[0].keys() == {"url", "category_code", "date_added", "source", "notes"}
    assert len(tl) > 1000
    return r.json


def test_list_unsupported_country(client, usersession):
    r = usersession.get("/api/_/url-submission/test-list/XY")
    assert r.status_code == 200
    assert r.json["test_list"] == None


def add_url(usersession, url, tmp_path):
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
        old_entry={},
        comment="Integ test: add example URL",
    )

    r = usersession.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.data

    r = usersession.get("/api/_/url-submission/test-list/us")
    assert r.status_code == 200
    tl = r.json["test_list"]
    en = [e for e in tl if e["url"] == url]
    assert len(en) == 1
    assert en[0] == new_entry


def lookup_and_delete_us_url(usersession, url):
    r = usersession.get("/api/_/url-submission/test-list/us")
    assert r.status_code == 200
    tl = r.json["test_list"]
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
        new_entry={},
        old_entry=old_entry,
        comment="Integ test: delete URL",
    )

    r = usersession.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.data


def test_update_url_reject(client, usersession):
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
    r = usersession.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 400, r.data


def test_update_url_nochange(client, usersession):
    r = usersession.get("/api/_/url-submission/test-list/it")
    assert r.status_code == 200
    tl = r.json["test_list"]

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
    r = usersession.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 400, r.data
    assert b"err_no_proposed_changes" in r.data


# TODO reset git
# TODO open PR
def update_url_basic(usersession):
    r = usersession.get("/api/_/url-submission/test-list/it")
    assert r.status_code == 200
    tl = r.json["test_list"]

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
    r = usersession.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.data

    assert get_state(usersession) == "IN_PROGRESS"


def delete_url(usersession):
    d = dict(
        country_code="US",
        old_entry={
            "url": "https://www.example.com/",
            "category_code": "FILE",
            "date_added": "2017-04-12",
            "source": "",
            "notes": "",
        },
        new_entry={},
        comment="delete example URL",
    )

    r = usersession.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.data


def get_state(usersession, cc="ie"):
    # state is independent from cc
    r = usersession.get(f"/api/_/url-submission/test-list/{cc}")
    assert r.status_code == 200
    return r.json["state"]


def test_pr_state(usersession):
    assert get_state(usersession) == "CLEAN"


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

    monkeypatch.setattr(ooniapi.citizenlab.URLListManager, "_push_to_repo", push)
    monkeypatch.setattr(ooniapi.citizenlab.requests, "post", req)
    monkeypatch.setattr(ooniapi.citizenlab.requests, "patch", req)
    monkeypatch.setattr(ooniapi.citizenlab.requests, "get", req)


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

    monkeypatch.setattr(ooniapi.citizenlab.URLListManager, "_push_to_repo", push)
    monkeypatch.setattr(ooniapi.citizenlab.requests, "post", req)
    monkeypatch.setattr(ooniapi.citizenlab.requests, "patch", req)
    monkeypatch.setattr(ooniapi.citizenlab.requests, "get", req)


@pytest.fixture
def clean_workdir(app, tmp_path):
    with app.app_context():
        assert app
        conf = ooniapi.citizenlab.current_app.config
        assert conf
        conf["GITHUB_WORKDIR"] = tmp_path.as_posix()


def _read_us_csv_file(tmp_path):
    # read from user repo path: citizenlab.py get_user_repo_path
    account_id = "ff266536c4bda24306b30187fca19f6b"
    f = tmp_path / "users" / account_id / "test-lists/lists/us.csv"
    return f.read_text().splitlines()


def _test_checkout_update_submit(usersession, tmp_path):
    assert get_state(usersession) == "CLEAN"

    r = list_global(usersession)
    assert r["state"] == "CLEAN"

    url = "https://example-bogus-1.org/"
    add_url(usersession, url, tmp_path)
    assert get_state(usersession) == "IN_PROGRESS"

    csv = _read_us_csv_file(tmp_path)
    assert csv[0] == "url,category_code,category_description,date_added,source,notes"
    assert url in csv[-1], "URL not found in the last line in the CSV file"

    r = usersession.get("/api/_/url-submission/test-list/us")
    assert r.status_code == 200

    assert len(r.json["changes"]["us"]) == 1

    add_url(usersession, "https://example-bogus.org/", tmp_path)
    lookup_and_delete_us_url(usersession, "https://example-bogus.org/")

    update_url_basic(usersession)

    r = usersession.post("/api/v1/url-submission/submit")
    assert r.status_code == 200

    # This is clean, because we are mocking the is_pr_resolved request, making
    # the test client believe that the PR has been merged.
    assert get_state(usersession) == "CLEAN"

    r = usersession.get("/api/_/url-submission/test-list/us")
    assert r.json["changes"] == {}


def test_checkout_update_submit(
    clean_workdir, client, usersession, mock_requests_closed, tmp_path
):
    _test_checkout_update_submit(usersession, tmp_path)

    # Before getting the list URLListManager will check if the mock PR is done
    # (it is) and set the state to CLEAN
    r = list_global(usersession)
    assert r["state"] == "CLEAN"


def test_propose_changes_then_update(
    clean_workdir, client, usersession, mock_requests_open, tmp_path
):
    assert get_state(usersession) == "CLEAN"

    url = "https://example-bogus-1.org/"
    add_url(usersession, url, tmp_path)
    assert get_state(usersession) == "IN_PROGRESS"

    r = usersession.post("/api/v1/url-submission/submit")
    assert r.status_code == 200

    assert get_state(usersession) == "PR_OPEN"

    url = "https://example-bogus-2.org/"
    add_url(usersession, url, tmp_path)
    assert get_state(usersession) == "IN_PROGRESS"

    r = usersession.post("/api/v1/url-submission/submit")
    assert r.status_code == 200

    assert get_state(usersession) == "PR_OPEN"


# # Tests with real GitHub # #


@pytest.mark.skipif(not pytest.run_ghpr, reason="use --ghpr to run")
def test_ghpr_checkout_update_submit(clean_workdir, usersession, tmp_path):
    _test_checkout_update_submit(usersession, tmp_path)
    # This is a *real* PR
    r = list_global(usersession)
    assert r["state"] == "PR_OPEN"


# # Prioritization management # #


def test_url_priorities_crud(adminsession, url_prio_tblready):
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
        assert r.status_code == 200, r.json
        match = [x for x in r.json["rules"] if x == exp]
        return len(match)

    assert match("INTEG-TEST") == 0
    assert match("INTEG-TEST2") == 0

    r = adminsession.get("/api/_/url-priorities/list")
    assert r.status_code == 200, r.json
    assert len(r.json["rules"]) > 20

    d = dict()
    r = adminsession.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 400, r.json

    # Create
    xxx = dict(category_code="NEWS", priority=100, url="INTEG-TEST")
    d = dict(new_entry=xxx)
    r = adminsession.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 200, r.json

    # Ensure the new entry is present
    assert match("INTEG-TEST") == 1

    # Fail to create a duplicate
    d = dict(new_entry=xxx)
    r = adminsession.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 400, r.json

    # Update (change URL)
    yyy = dict(category_code="NEWS", priority=100, url="INTEG-TEST2")
    d = dict(old_entry=xxx, new_entry=yyy)
    r = adminsession.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 200, r.json
    assert match("INTEG-TEST") == 0
    assert match("INTEG-TEST2") == 1

    # Delete
    d = dict(old_entry=yyy)
    r = adminsession.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 200, r.json
    assert r.json == 1

    assert match("INTEG-TEST") == 0
    assert match("INTEG-TEST2") == 0


def post(client, url, **kw):
    return client.post(url, json=kw)


def post200(client, url, **kw):
    r = post(client, url, **kw)
    assert r.status_code == 200, r.json
    return r


def test_x(client, adminsession):
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


def test_url_prioritization(client):
    c = getjson(client, "/api/v1/test-list/urls?limit=100")
    assert "metadata" in c
    assert c["metadata"]["count"] > 1
    c["metadata"]["count"] = 0
    assert c["metadata"] == {
        "count": 0,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }

    assert set(r["url"] for r in c["results"])


def test_url_prioritization_category_code(client, citizenlab_tblready):
    c = getjson(client, "/api/v1/test-list/urls?category_codes=NEWS&limit=100")
    assert "metadata" in c
    for r in c["results"]:
        assert r["category_code"] == "NEWS"

    assert set(r["url"] for r in c["results"])


def test_url_prioritization_category_codes(client, citizenlab_tblready):
    c = getjson(
        client,
        "/api/v1/test-list/urls?category_codes=NEWS,HUMR&country_code=US&limit=100",
    )
    assert "metadata" in c
    for r in c["results"]:
        assert r["category_code"] in ("NEWS", "HUMR")

    assert set(r["url"] for r in c["results"])


def test_url_prioritization_country_code_limit(client):
    c = getjson(client, "/api/v1/test-list/urls?country_code=US&limit=999")
    assert "metadata" in c
    assert c["metadata"]["count"] > 1
    c["metadata"]["count"] = 0
    assert c["metadata"] == {
        "count": 0,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["country_code"] in ("XX", "US")

    assert len(set(r["url"] for r in c["results"])) > 1


def test_url_prioritization_country_code_nolimit(client, url_prio_tblready):
    c = getjson(client, "/api/v1/test-list/urls?country_code=US")
    assert "metadata" in c
    assert sum(1 for r in c["results"] if r["country_code"] == "XX")
