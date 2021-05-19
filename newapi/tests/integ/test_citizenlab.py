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
    assert r.json[0] == [
        "url",
        "category_code",
        "category_description",
        "date_added",
        "source",
        "notes",
    ]
    assert len(r.json) > 1000


def add_url(client, usersession):
    d = dict(
        country_code="US",
        new_entry=[
            "https://www.example.com/",
            "FILE",
            "File-sharing",
            "2017-04-12",
            "",
            "",
        ],
        comment="add example URL",
    )

    r = client.post("/api/v1/url-submission/add-url", json=d)
    assert r.status_code == 200, r.data


def test_update_url_reject(client, usersession):
    d = dict(
        country_code="it",
        old_entry=[
            "http://btdigg.org/",
            "FILE",
            "File-sharing",
            "2017-04-12",
            "",
            "<bogus value not matching anything>",
        ],
        new_entry=[
            "https://btdigg.org/",
            "FILE",
            "File-sharing",
            "2017-04-12",
            "",
            "Meow",
        ],
        comment="add HTTPS to the website url",
    )
    r = client.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 400, r.data


def test_update_url_nochange(client, usersession):
    r = client.get("/api/v1/url-submission/test-list/it")
    assert r.status_code == 200

    old = r.json[1]  # first entry, skip header
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

    old = r.json[1]  # first entry, skip header
    new = list(old)
    new[-1] = "Bogus comment"
    assert new != old
    d = dict(country_code="it", old_entry=old, new_entry=new, comment="")
    r = client.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.data

    assert get_state(client) == "IN_PROGRESS"


def get_state(client):
    r = client.get("/api/v1/url-submission/state")
    assert r.status_code == 200
    return r.json["state"]


def test_pr_state(client, usersession):
    assert get_state(client) == "CLEAN"


# # Tests with mocked-out GitHub # #


class MK:
    @staticmethod
    def json():  # mock both openin a pr or checking its status
        return {"state": "closed", "url": "testurl"}


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


@pytest.fixture
def clean_workdir(app, tmp_path):
    with app.app_context():
        assert app
        conf = ooniapi.citizenlab.current_app.config
        assert conf
        conf["GITHUB_WORKDIR"] = tmp_path.as_posix()


def test_checkout_update_submit(clean_workdir, client, usersession, mock_requests):
    assert get_state(client) == "CLEAN"

    list_global(client, usersession)
    assert get_state(client) == "CLEAN"

    add_url(client, usersession)
    assert get_state(client) == "IN_PROGRESS"

    update_url_basic(client, usersession)

    r = client.post("/api/v1/url-submission/submit")
    assert r.status_code == 200

    assert get_state(client) == "PR_OPEN"

    # Before getting the list URLListManager will check if the PR is done
    # (it is) and set the state to CLEAN
    list_global(client, usersession)
    assert get_state(client) == "CLEAN"


# # Tests with real GitHub # #


@pytest.mark.skipif(not pytest.run_ghpr, reason="use --ghpr to run")
def test_ghpr_checkout_update_submit(clean_workdir, client, usersession):
    assert get_state(client) == "CLEAN"

    list_global(client, usersession)
    assert get_state(client) == "CLEAN"

    add_url(client, usersession)
    assert get_state(client) == "IN_PROGRESS"

    update_url_basic(client, usersession)

    r = client.post("/api/v1/url-submission/submit")
    assert r.status_code == 200

    assert get_state(client) == "PR_OPEN"

    list_global(client, usersession)
    assert get_state(client) == "PR_OPEN"


# # Prioritization management # #


def test_url_priorities_list(client, adminsession):
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

    r = client.get("/api/_/url-priorities/WIP")
    assert r.json
    for e in r.json:
        if e["category_code"] == "NEWS" and e["cc"] == "it" and e["url"] == 'http://www.leggo.it/':
            assert e["priority"] == 118  # 4 rules matched

    post200(client, "/api/_/url-priorities/update", old_entry=xxx)
    post200(client, "/api/_/url-priorities/update", old_entry=yyy)
    post200(client, "/api/_/url-priorities/update", old_entry=zzz)
