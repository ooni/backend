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
from .test_integration_auth import adminsession
from tests.utils import *

# setup_test_session mocks SMTP when the test session starts


@pytest.fixture
def usersession(client):
    # Mock out SMTP, register a user and log in
    user_e = "nick@localhost.local"
    reset_smtp_mock()
    _register_and_login(client, user_e)
    reset_smtp_mock()
    yield
    reset_smtp_mock()


def test_no_auth(client):
    r = client.get("/api/v1/url-submission/test-list/global")
    assert r.status_code == 401


def list_global(client, usersession):
    r = client.get("/api/v1/url-submission/test-list/global")
    assert r.status_code == 200
    assert r.json[0].keys() == {"url", "category_code", "date_added", "source", "notes"}
    assert len(r.json) > 1000


def add_url(client, usersession, url, tmp_path):
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

    r = client.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.data

    r = client.get("/api/v1/url-submission/test-list/us")
    assert r.status_code == 200
    en = [e for e in r.json if e["url"] == url]
    assert len(en) == 1
    assert en[0] == new_entry


def lookup_and_delete_us_url(client, usersession, url):
    r = client.get("/api/v1/url-submission/test-list/us")
    assert r.status_code == 200
    en = [e for e in r.json if e["url"] == url]
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

    r = client.post("/api/v1/url-submission/update-url", json=d)
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
    r = client.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 400, r.data


def test_update_url_nochange(client, usersession):
    r = client.get("/api/v1/url-submission/test-list/it")
    assert r.status_code == 200

    fe = r.json[0]  # first entry
    old = {
        "url": fe["url"],
        "category_code": fe["category_code"],
        "date_added": fe["date_added"],
        "source": fe["source"],
        "notes": fe["notes"],
    }
    new = old
    d = dict(country_code="it", old_entry=old, new_entry=new, comment="")
    r = client.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 400, r.data
    assert b"No change is" in r.data


# TODO reset git
# TODO open PR
def update_url_basic(client, usersession):
    r = client.get("/api/v1/url-submission/test-list/it")
    assert r.status_code == 200

    fe = r.json[0]  # first entry
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
    r = client.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.data

    assert get_state(client) == "IN_PROGRESS"


def delete_url(client, usersession):
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

    r = client.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.data


def get_state(client):
    r = client.get("/api/v1/url-submission/state")
    assert r.status_code == 200
    return r.json["state"]


def get_diff(client):
    r = client.get("/api/v1/url-submission/diff")
    assert r.status_code == 200
    return r.json["diff"]


def test_pr_state(client, usersession):
    assert get_state(client) == "CLEAN"


# # Tests with mocked-out GitHub # #


class MK:
    @staticmethod
    def json():  # mock both openin a pr or checking its status
        return {"state": "closed", "url": "https://testurl"}


@pytest.fixture
def mock_requests(monkeypatch):
    def req(*a, **kw):
        print(a)
        print(kw)
        return MK()

    def push(*a, **kw):
        print(a)
        print(kw)
        return MK()

    monkeypatch.setattr(ooniapi.citizenlab.URLListManager, "push_to_repo", push)
    monkeypatch.setattr(ooniapi.citizenlab.requests, "post", req)
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


def _test_checkout_update_submit(client, tmp_path):
    assert get_state(client) == "CLEAN"

    list_global(client, usersession)
    assert get_state(client) == "CLEAN"

    assert get_diff(client) == []

    url = "https://example-bogus-1.org/"
    add_url(client, usersession, url, tmp_path)
    assert get_state(client) == "IN_PROGRESS"

    csv = _read_us_csv_file(tmp_path)
    assert csv[0] == "url,category_code,category_description,date_added,source,notes"
    assert url in csv[-1], "URL not found in the last line in the CSV file"

    # assert get_diff(client) != []


    add_url(client, usersession, "https://example-bogus.org/", tmp_path)
    lookup_and_delete_us_url(client, usersession, "https://example-bogus.org/")

    update_url_basic(client, usersession)

    r = client.post("/api/v1/url-submission/submit")
    assert r.status_code == 200

    # This is clean, because we are mocking the is_pr_resolved request, making
    # the test client believe that the PR has been merged.
    assert get_state(client) == "CLEAN"


def test_checkout_update_submit(
    clean_workdir, client, usersession, mock_requests, tmp_path
):
    _test_checkout_update_submit(client, tmp_path)

    # Before getting the list URLListManager will check if the mock PR is done
    # (it is) and set the state to CLEAN
    list_global(client, usersession)
    assert get_state(client) == "CLEAN"


# # Tests with real GitHub # #


@pytest.mark.skipif(not pytest.run_ghpr, reason="use --ghpr to run")
def test_ghpr_checkout_update_submit(clean_workdir, client, usersession, tmp_path):
    _test_checkout_update_submit(client, tmp_path)
    # This is a *real* PR
    list_global(client, usersession)
    assert get_state(client) == "PR_OPEN"


# # Prioritization management # #


def test_url_priorities_crud(client, adminsession):
    def match(url):
        exp = {
            "category_code": "NEWS",
            "cc": "*",
            "domain": "*",
            "priority": 100,
            "url": url,
        }
        r = client.get("/api/_/url-priorities/list")
        assert r.status_code == 200, r.json
        match = [x for x in r.json["rules"] if x == exp]
        return len(match)

    assert match("BOGUSTEST") == 0
    assert match("BOGUSTEST2") == 0

    r = client.get("/api/_/url-priorities/list")
    assert r.status_code == 200, r.json
    assert len(r.json["rules"]) > 20

    d = dict()
    r = client.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 400, r.json

    # Create
    xxx = dict(category_code="NEWS", priority=100, url="BOGUSTEST")
    d = dict(new_entry=xxx)
    r = client.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 200, r.json
    assert r.json == 1

    # Ensure the new entry is present
    assert match("BOGUSTEST") == 1

    # Fail to create a duplicate
    d = dict(new_entry=xxx)
    r = client.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 400, r.json

    # Update
    yyy = dict(category_code="NEWS", priority=100, url="BOGUSTEST2")
    d = dict(old_entry=xxx, new_entry=yyy)
    r = client.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 200, r.json
    assert match("BOGUSTEST") == 0
    assert match("BOGUSTEST2") == 1

    # Delete
    d = dict(old_entry=yyy)
    r = client.post("/api/_/url-priorities/update", json=d)
    assert r.status_code == 200, r.json
    assert r.json == 1

    assert match("BOGUSTEST") == 0
    assert match("BOGUSTEST2") == 0


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

    post(client, "/api/_/url-priorities/update", old_entry=xxx)
    post(client, "/api/_/url-priorities/update", old_entry=yyy)
    post(client, "/api/_/url-priorities/update", old_entry=zzz)

    post200(client, "/api/_/url-priorities/update", new_entry=xxx)
    post200(client, "/api/_/url-priorities/update", new_entry=yyy)
    post200(client, "/api/_/url-priorities/update", new_entry=zzz)

    ## XXX currently broken
    # r = client.get("/api/_/url-priorities/WIP")
    # assert r.json
    # for e in r.json:
    #    if e["category_code"] == "NEWS" and e["cc"] == "it" and e["url"] == 'http://www.leggo.it/':
    #        assert e["priority"] == 118  # 4 rules matched

    post200(client, "/api/_/url-priorities/update", old_entry=xxx)
    post200(client, "/api/_/url-priorities/update", old_entry=yyy)
    post200(client, "/api/_/url-priorities/update", old_entry=zzz)


def test_url_prioritization(client):
    c = getjson(client, "/api/v1/test-list/urls?limit=100")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 100,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }

    assert len(set(r["url"] for r in c["results"])) == 100


def test_url_prioritization_category_code(client):
    c = getjson(client, "/api/v1/test-list/urls?category_codes=NEWS&limit=100")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 100,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["category_code"] == "NEWS"

    assert len(set(r["url"] for r in c["results"])) == 100


def test_url_prioritization_category_codes(client):
    c = getjson(
        client,
        "/api/v1/test-list/urls?category_codes=NEWS,HUMR&country_code=US&limit=100",
    )
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 100,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["category_code"] in ("NEWS", "HUMR")

    assert len(set(r["url"] for r in c["results"])) == 100


def test_url_prioritization_country_code_limit(client):
    c = getjson(client, "/api/v1/test-list/urls?country_code=US&limit=999")
    assert "metadata" in c
    assert c["metadata"] == {
        "count": 999,
        "current_page": -1,
        "limit": -1,
        "next_url": "",
        "pages": 1,
    }
    for r in c["results"]:
        assert r["country_code"] in ("XX", "US")

    assert len(set(r["url"] for r in c["results"])) == 999


def test_url_prioritization_country_code_nolimit(client):
    c = getjson(client, "/api/v1/test-list/urls?country_code=US")
    assert "metadata" in c
    xx_cnt = 0
    for r in c["results"]:
        assert r["country_code"] in ("XX", "US")
        if r["country_code"] == "XX":
            xx_cnt += 1

    assert xx_cnt > 1200
    us_cnt = c["metadata"]["count"] - xx_cnt
    assert us_cnt > 40
