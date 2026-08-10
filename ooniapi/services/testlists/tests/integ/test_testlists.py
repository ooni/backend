"""
Integration test for Citizenlab API

Warning: this test runs against GitHub and opens PRs

Warning: writes git repos on disk

Lint using Black.

Test using:
    hatch run test
"""

import csv
import io
import os

from pathlib import Path

import pytest

# debdeps: python3-pytest-mock

from dulwich import porcelain as dulwich_git
from dulwich.objects import Blob, Commit, Tree
from filelock import FileLock

import testlists.manager
from tests.conftest import create_session_token


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

    monkeypatch.setattr(testlists.manager.URLListManager, "_push_to_repo", push)
    monkeypatch.setattr(testlists.manager.requests, "post", req)
    monkeypatch.setattr(testlists.manager.requests, "patch", req)
    monkeypatch.setattr(testlists.manager.requests, "get", req)


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

    monkeypatch.setattr(testlists.manager.URLListManager, "_push_to_repo", push)
    monkeypatch.setattr(testlists.manager.requests, "post", req)
    monkeypatch.setattr(testlists.manager.requests, "patch", req)
    monkeypatch.setattr(testlists.manager.requests, "get", req)


def _read_us_csv_file(tmp_path):
    # read from user repo path: testlists.py get_user_repo_path
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


# # Regression tests for the "PR missing the latest change" bug # #
#
# test_propose_changes_then_update above already exercises the
# create-submission -> add-more-urls -> resubmit state machine, but it uses
# mock_requests_open, which stubs out URLListManager._push_to_repo
# entirely (see mock_requests_open/mock_requests_closed above). That means
# none of the existing tests in this file - including the default (no
# --ghpr) CI run - ever look at what actually lands on the pushed branch.
# That's exactly the layer the "worktree has the change, but the branch/PR
# doesn't" bug lived in, and why it shipped unnoticed. The fixtures and
# tests below exercise the real dulwich clone/worktree/commit/push
# mechanics against local bare repos (no network/GitHub credentials
# needed) so this class of bug gets caught by the regular test suite.


@pytest.fixture
def mock_github_pr_api(monkeypatch):
    """Mock only the GitHub REST calls used to open/close/poll a PR
    (POST .../pulls, PATCH .../pulls/N, GET .../pulls/N).

    Unlike mock_requests_open/mock_requests_closed above, this does NOT
    stub out _push_to_repo, so tests using this fixture exercise the real
    dulwich commit/push path.
    """

    def req(*a, **kw):
        return MKOpen()

    monkeypatch.setattr(testlists.manager.requests, "post", req)
    monkeypatch.setattr(testlists.manager.requests, "patch", req)
    monkeypatch.setattr(testlists.manager.requests, "get", req)


@pytest.fixture
def local_test_lists_remotes(tmp_path_factory):
    """Stand-in for citizenlab/test-lists ("origin") and ooni-bot/test-lists
    ("push", i.e. the bot's fork) as two local bare repos, seeded with a
    minimal set of CSV files. This lets tests exercise dulwich's real
    clone/worktree/commit/push mechanics without touching the network or a
    real GitHub repo.
    """
    base = tmp_path_factory.mktemp("local_remotes")
    origin_bare = base / "origin.git"
    push_bare = base / "push.git"
    seed = base / "seed"

    seed.mkdir()
    dulwich_git.init(str(seed))
    (seed / "lists").mkdir()
    header = "url,category_code,category_description,date_added,source,notes\n"
    country_codes = ("us", "it", "ie", "global")
    csv_paths = []
    for cc in country_codes:
        p = seed / "lists" / f"{cc}.csv"
        p.write_text(header)
        csv_paths.append(str(p))
    dulwich_git.add(str(seed), paths=csv_paths)
    dulwich_git.commit(
        str(seed),
        message="seed",
        author=b"seed <seed@example.com>",
        committer=b"seed <seed@example.com>",
    )

    dulwich_git.init(str(origin_bare), bare=True)
    dulwich_git.init(str(push_bare), bare=True)
    dulwich_git.push(str(seed), str(origin_bare), refspecs=["master:master"])

    return {"origin": str(origin_bare), "push": str(push_bare)}


@pytest.fixture
def use_local_git_remotes(monkeypatch, local_test_lists_remotes):
    """Redirect URLListManager._init_repo at the two local bare repos from
    local_test_lists_remotes instead of contacting github.com. The
    push_repo/origin_repo strings in test_settings (conftest.py) are left
    as-is; they're only used to build the GitHub API URLs, which are
    themselves mocked out by mock_github_pr_api.

    Also pins a stable git identity via LOGNAME/EMAIL env vars. This is a
    *different* code path from the author=/committer= manager.update() now
    passes explicitly to git.commit(): dulwich also writes a reflog entry
    for every ref imported during clone()/fetch() (and for new branches
    created by worktree_add()), and that reflog write resolves identity
    via get_user_identity(config) with no kind= argument - which skips the
    GIT_AUTHOR_*/GIT_COMMITTER_* env var check entirely and falls straight
    to git config, then LOGNAME/USER/EMAIL + /etc/passwd. A CI runner with
    none of those configured hits dulwich.repo.DefaultIdentityNotFound on
    the very first clone, independent of anything manager.py does - this
    showed up as a real CI failure once these tests started actually
    exercising git.clone() instead of mocking it away.
    """
    monkeypatch.setenv("LOGNAME", "testlists-ci")
    monkeypatch.setenv("EMAIL", "testlists-ci@example.com")

    def fake_init_repo(self):
        if not os.path.exists(self.repo_dir):
            dulwich_git.clone(
                local_test_lists_remotes["origin"], self.repo_dir, branch="master"
            )
            dulwich_git.remote_add(
                self.repo_dir, "rworigin", local_test_lists_remotes["push"]
            )
        repo = dulwich_git.Repo(self.repo_dir)
        dulwich_git.pull(repo, "origin", "master")

    monkeypatch.setattr(testlists.manager.URLListManager, "_init_repo", fake_init_repo)


def _read_csv_from_repo(repo_path, branch, cc):
    """Read a file's content directly off a branch in a local bare repo -
    i.e. bypass the API/manager entirely and inspect exactly what's
    actually there, the same way a GitHub PR review (or a post-merge
    checkout of master) would see it."""
    with dulwich_git.Repo(repo_path) as repo:
        commit = repo[f"refs/heads/{branch}".encode()]
        tree = repo[commit.tree]
        _mode, blob_sha = tree.lookup_path(
            repo.object_store.__getitem__, f"lists/{cc}.csv".encode()
        )
        return repo[blob_sha].data.decode()


def _read_pushed_csv(local_test_lists_remotes, branch, cc):
    """Read a file's content directly off a branch in the local bare
    "push" repo (i.e. the bot's fork, what a PR is opened from)."""
    return _read_csv_from_repo(local_test_lists_remotes["push"], branch, cc)


def _merge_csv_union(*contents):
    """Union-merge CSV contents by the "url" column: first-seen order is
    kept, and a later occurrence of the same url overrides the earlier
    row's data. Stands in for a maintainer manually resolving a (typically
    trivial, line-level) merge conflict between two independently-authored
    CSV changes before accepting a PR - as opposed to a raw force-push of
    one branch's tip over the other, which would silently discard
    whichever side isn't a git ancestor of the other.
    """
    seen = {}
    order = []
    fieldnames = None
    for content in contents:
        reader = csv.DictReader(io.StringIO(content))
        if fieldnames is None:
            fieldnames = reader.fieldnames
        for row in reader:
            url = row["url"]
            if url not in seen:
                order.append(url)
            seen[url] = row
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for url in order:
        writer.writerow(seen[url])
    return out.getvalue()


def _simulate_maintainer_merge(origin_repo_path, push_repo_path, branch, cc="us"):
    """Simulate a GitHub maintainer merging `branch` (from the bot's fork,
    the "push" repo) into origin's master, producing a new commit on
    master whose tree combines master's current content for
    `lists/<cc>.csv` with the branch's content for the same file, via
    _merge_csv_union().

    A plain `dulwich.porcelain.push(push_repo, origin_repo,
    refspecs=[f"...{branch}:refs/heads/master"])` only works for a clean
    fast-forward (i.e. master hasn't moved since the branch was cut) and
    raises DivergedBranches otherwise; force=True would "succeed" but
    silently replace master's tree with the branch's tree wholesale,
    discarding any content on master that isn't in the branch's own
    history - exactly the already-merged content from a previous,
    unrelated user's PR. A real GitHub merge doesn't do that: either it's
    a fast-forward, or a human resolves the (typically trivial) conflict
    and the resulting merge commit's tree reflects both sides. This
    builds that resulting tree directly at the object level so tests can
    assert on it without needing a real GitHub merge.
    """
    with dulwich_git.Repo(origin_repo_path) as origin, dulwich_git.Repo(
        push_repo_path
    ) as push:
        master_tip = origin.refs[b"refs/heads/master"]
        master_tree = origin[origin[master_tip].tree]
        _, master_blob_sha = master_tree.lookup_path(
            origin.object_store.__getitem__, f"lists/{cc}.csv".encode()
        )
        master_csv = origin[master_blob_sha].data.decode()

        branch_tip = push.refs[f"refs/heads/{branch}".encode()]
        branch_tree = push[push[branch_tip].tree]
        _, branch_blob_sha = branch_tree.lookup_path(
            push.object_store.__getitem__, f"lists/{cc}.csv".encode()
        )
        branch_csv = push[branch_blob_sha].data.decode()

        merged_csv = _merge_csv_union(master_csv, branch_csv)

        new_blob = Blob.from_string(merged_csv.encode())
        origin.object_store.add_object(new_blob)

        _, lists_tree_sha = master_tree.lookup_path(
            origin.object_store.__getitem__, b"lists"
        )
        lists_tree = origin[lists_tree_sha]
        new_lists_tree = Tree()
        for name, mode, sha in lists_tree.iteritems():
            new_lists_tree.add(
                name, mode, new_blob.id if name == f"{cc}.csv".encode() else sha
            )
        origin.object_store.add_object(new_lists_tree)

        new_root_tree = Tree()
        for name, mode, sha in master_tree.iteritems():
            new_root_tree.add(
                name, mode, new_lists_tree.id if name == b"lists" else sha
            )
        origin.object_store.add_object(new_root_tree)

        identity = b"maintainer <maintainer@example.com>"
        new_commit = Commit()
        new_commit.tree = new_root_tree.id
        new_commit.parents = [master_tip]
        new_commit.author = new_commit.committer = identity
        new_commit.author_time = new_commit.commit_time = 1700000000
        new_commit.author_timezone = new_commit.commit_timezone = 0
        new_commit.encoding = b"UTF-8"
        new_commit.message = f"Merge {branch} into master".encode()
        origin.object_store.add_object(new_commit)

        origin.refs[b"refs/heads/master"] = new_commit.id


def test_submit_then_add_more_urls_then_resubmit_pushes_all_changes(
    client_with_user_role,
    mock_github_pr_api,
    use_local_git_remotes,
    local_test_lists_remotes,
    tmp_path,
):
    """The scenario from the original bug report: a user creates a
    submission, submits it (opening a PR), adds more URLs to the same
    in-progress submission, and submits again. The re-pushed branch must
    contain every change made so far, not just the latest one (or worse,
    none of them, if a git.add()/git.commit() failure silently left the
    branch stuck on an older commit while the API still reported success).
    """
    account_id = "0" * 16  # matches create_session_token() in conftest.py
    branch = f"user-contribution/{account_id}"

    assert get_state(client_with_user_role) == "CLEAN"

    url_a = "https://example-a.org/"
    add_url(client_with_user_role, url_a, tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "PR_OPEN"

    pushed = _read_pushed_csv(local_test_lists_remotes, branch, "us")
    assert url_a in pushed, "first submission never made it to the pushed branch"

    # Add a second URL to the same in-progress submission. Since the state
    # is PR_OPEN, update() will close the existing PR (mocked) before
    # committing this change, then submit() re-pushes the branch.
    url_b = "https://example-b.org/"
    add_url(client_with_user_role, url_b, tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "PR_OPEN"

    # This is the exact symptom from the bug report: the re-pushed branch
    # must contain BOTH urls, not just the latest edit (or, in the worst
    # case observed in production, neither).
    pushed_again = _read_pushed_csv(local_test_lists_remotes, branch, "us")
    assert url_a in pushed_again, "first URL missing from the re-pushed branch"
    assert url_b in pushed_again, "second URL missing from the re-pushed branch"


def test_duplicate_url_rejection_does_not_block_further_submissions(
    client_with_user_role,
    mock_github_pr_api,
    use_local_git_remotes,
    local_test_lists_remotes,
    tmp_path,
):
    """A failed attempt to add a URL that's already been accepted must not
    corrupt the account's state or prevent it from making further, valid
    submissions.

    This exercises a subtlety in update(): when the account's state is
    PR_OPEN, update() closes the existing PR and flips the state to
    IN_PROGRESS *before* it checks for a duplicate URL. So a rejected
    duplicate-add still has the (harmless, from the user's perspective)
    side effect of closing whatever PR was open - the account ends up
    IN_PROGRESS rather than back at PR_OPEN. What actually matters, and
    what this test checks, is that this side effect is benign: the
    previously-accepted change is never lost or altered, submit() can
    still be called again to re-open a PR containing it, and adding a
    genuinely new URL afterwards works too - all without ever creating a
    duplicate row.
    """
    account_id = "0" * 16  # matches create_session_token() in conftest.py
    branch = f"user-contribution/{account_id}"

    assert get_state(client_with_user_role) == "CLEAN"

    # --- Submit and accept a first URL.
    url_1 = "https://first-accepted.org/"
    add_url(client_with_user_role, url_1, tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "PR_OPEN"

    pushed_first = _read_pushed_csv(local_test_lists_remotes, branch, "us")
    assert url_1 in pushed_first

    # --- Attempt to add the SAME url again. This must fail...
    dup_entry = {
        "url": url_1,
        "category_code": "FILE",
        "date_added": "2017-04-12",
        "source": "",
        "notes": "duplicate attempt",
    }
    d = dict(
        country_code="US",
        new_entry=dup_entry,
        comment="Integ test: attempt duplicate URL",
    )
    r = client_with_user_role.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 400, r.json()
    assert b"err_duplicate_url" in r.content

    # ...and it must not have snuck the duplicate row in anyway, nor left
    # the account somewhere broken/unusable. (The rejected duplicate does
    # still close the previously-open PR as a documented side effect of
    # update() checking state before validating the entry - see the
    # docstring above - so this is IN_PROGRESS, not PR_OPEN, at this
    # point.)
    assert get_state(client_with_user_role) == "IN_PROGRESS"
    tl_after_dup = client_with_user_role.get(
        "/api/_/url-submission/test-list/us"
    ).json()["test_list"]
    assert sum(1 for e in tl_after_dup if e["url"] == url_1) == 1, (
        "the rejected duplicate must not have been written to the list twice"
    )

    # --- The already-accepted change must still be submittable: re-push
    # and re-open a PR containing it, exactly as if the failed duplicate
    # attempt had never happened.
    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "PR_OPEN"

    pushed_after_dup = _read_pushed_csv(local_test_lists_remotes, branch, "us")
    assert url_1 in pushed_after_dup, (
        "the previously-accepted URL must survive a rejected duplicate "
        "attempt and a resubmission"
    )
    assert pushed_after_dup.count(url_1) == 1, (
        "the previously-accepted URL must not have been duplicated on the "
        "pushed branch either"
    )

    # --- And a genuinely different URL must still be addable and
    # submittable afterwards, ending up alongside the first one with no
    # duplication.
    url_2 = "https://second-accepted.org/"
    add_url(client_with_user_role, url_2, tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "PR_OPEN"

    pushed_final = _read_pushed_csv(local_test_lists_remotes, branch, "us")
    assert url_1 in pushed_final
    assert url_2 in pushed_final
    assert pushed_final.count(url_1) == 1
    assert pushed_final.count(url_2) == 1


def test_delete_entry_full_lifecycle_through_real_git(
    client_with_user_role,
    mock_github_pr_api,
    use_local_git_remotes,
    local_test_lists_remotes,
    tmp_path,
):
    """Deleting an existing entry (old_entry set, new_entry absent) must
    flow through the real git commit/push path exactly like adding one
    does. Until now only the "add" branch of update()'s CSV-rewrite loop
    was exercised against real dulwich clone/worktree/commit/push
    mechanics; deletion takes a different branch (the matched row is
    simply never re-written) and deserves the same end-to-end coverage.
    """
    account_id = "0" * 16
    branch = f"user-contribution/{account_id}"

    url_to_delete = "https://will-be-deleted.org/"
    add_url(client_with_user_role, url_to_delete, tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "PR_OPEN"

    pushed_before_delete = _read_pushed_csv(local_test_lists_remotes, branch, "us")
    assert url_to_delete in pushed_before_delete

    # Delete it. Since state is PR_OPEN, update() closes the existing PR
    # first (mocked) before processing the deletion.
    lookup_and_delete_us_url(client_with_user_role, url_to_delete)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "PR_OPEN"

    pushed_after_delete = _read_pushed_csv(local_test_lists_remotes, branch, "us")
    assert url_to_delete not in pushed_after_delete, (
        "the deleted URL must not still be on the re-pushed branch"
    )
    assert pushed_after_delete.startswith(
        "url,category_code,category_description,date_added,source,notes\n"
    ), "the header row must still be intact after a delete-only change"


def test_update_existing_entry_full_lifecycle_through_real_git(
    client_with_user_role,
    mock_github_pr_api,
    use_local_git_remotes,
    local_test_lists_remotes,
    tmp_path,
):
    """Editing an existing entry (old_entry AND new_entry both set, same
    URL) must also flow through the real git commit/push path. This
    exercises the third branch of update()'s CSV-rewrite loop (the row
    matching old_entry is replaced with new_entry, in place) against a
    real dulwich commit, which the other real-git tests never touch since
    they only ever add.
    """
    account_id = "0" * 16
    branch = f"user-contribution/{account_id}"

    url = "https://will-be-edited.org/"
    add_url(client_with_user_role, url, tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "PR_OPEN"

    pushed_before_edit = _read_pushed_csv(local_test_lists_remotes, branch, "us")
    assert f"{url},FILE,File-sharing,2017-04-12,,Integ test\n" in pushed_before_edit

    # Fetch the exact current entry and edit its notes; the URL itself
    # stays the same, so this doesn't touch the duplicate-URL check.
    r = client_with_user_role.get("/api/_/url-submission/test-list/us")
    assert r.status_code == 200
    tl = r.json()["test_list"]
    old_entry = next(e for e in tl if e["url"] == url)
    new_entry = dict(old_entry, notes="Edited via integ test")

    d = dict(
        country_code="US",
        old_entry=old_entry,
        new_entry=new_entry,
        comment="Integ test: edit notes",
    )
    r = client_with_user_role.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "PR_OPEN"

    pushed_after_edit = _read_pushed_csv(local_test_lists_remotes, branch, "us")
    assert (
        f"{url},FILE,File-sharing,2017-04-12,,Edited via integ test\n"
        in pushed_after_edit
    )
    assert (
        f"{url},FILE,File-sharing,2017-04-12,,Integ test\n" not in pushed_after_edit
    ), "the pre-edit row must be gone, not just appended alongside the new one"
    assert pushed_after_edit.count(url) == 1, (
        "editing must replace the row in place, not leave two rows for this URL"
    )


def test_submission_spanning_two_country_codes_lands_both_in_one_push(
    client_with_user_role,
    mock_github_pr_api,
    use_local_git_remotes,
    local_test_lists_remotes,
    tmp_path,
):
    """A single in-progress submission can touch more than one country's
    CSV file before ever being submitted - e.g. a user adds a URL to "us"
    and, in the same sitting, another to "it". Both edits become separate
    commits on the same per-account branch; submit() pushes that branch
    once, and it must carry both files' changes together, each landing
    only in its own file.
    """
    account_id = "0" * 16
    branch = f"user-contribution/{account_id}"

    url_us = "https://two-cc-us.org/"
    url_it = "https://two-cc-it.org/"

    assert get_state(client_with_user_role) == "CLEAN"

    d_us = dict(
        country_code="US",
        new_entry={
            "url": url_us,
            "category_code": "FILE",
            "date_added": "2017-04-12",
            "source": "",
            "notes": "US entry",
        },
        comment="add US url",
    )
    r = client_with_user_role.post("/api/v1/url-submission/update-url", json=d_us)
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    d_it = dict(
        country_code="IT",
        new_entry={
            "url": url_it,
            "category_code": "FILE",
            "date_added": "2017-04-12",
            "source": "",
            "notes": "IT entry",
        },
        comment="add IT url",
    )
    r = client_with_user_role.post("/api/v1/url-submission/update-url", json=d_it)
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "PR_OPEN"

    pushed_us = _read_pushed_csv(local_test_lists_remotes, branch, "us")
    pushed_it = _read_pushed_csv(local_test_lists_remotes, branch, "it")
    assert url_us in pushed_us
    assert url_it in pushed_it
    assert url_it not in pushed_us, "the IT addition must not leak into the US file"
    assert url_us not in pushed_it, "the US addition must not leak into the IT file"


def test_duplicate_check_covers_global_but_not_the_reverse(
    client_with_user_role,
):
    """_prevent_duplicate_url() checks a country-specific submission
    against BOTH that country's own list and the "global" list, since a
    URL that's already globally relevant shouldn't be re-added
    per-country too. But the check is one-directional: adding to
    "global" is only checked against the existing global list, not
    against every individual country's list. This documents that
    asymmetry precisely rather than assuming duplicate detection is fully
    symmetric across all lists.
    """

    def add(cc, url, notes):
        d = dict(
            country_code=cc,
            new_entry={
                "url": url,
                "category_code": "FILE",
                "date_added": "2017-04-12",
                "source": "",
                "notes": notes,
            },
            comment=f"add {url} to {cc}",
        )
        return client_with_user_role.post("/api/v1/url-submission/update-url", json=d)

    # A URL already in "global" must be rejected as a duplicate when
    # someone tries to add the exact same URL to a specific country too.
    url_global = "https://already-global.org/"
    r = add("global", url_global, "global entry")
    assert r.status_code == 200, r.json()

    r = add("us", url_global, "duplicate via us")
    assert r.status_code == 400, r.json()
    assert b"err_duplicate_url" in r.content

    # The reverse is NOT checked: a URL already in a country-specific
    # list can still be added to "global" without being flagged.
    url_country = "https://already-in-us.org/"
    r = add("us", url_country, "us entry")
    assert r.status_code == 200, r.json()

    r = add("global", url_country, "not flagged as duplicate")
    assert r.status_code == 200, (
        f"expected the global-list add to succeed even though the same URL "
        f"already exists in the us list - _prevent_duplicate_url only "
        f"extends its check with the global list when adding to a "
        f"*country*, not the other direction; if this now fails, duplicate "
        f"detection has been made symmetric and this test should be "
        f"updated to assert the new behavior instead. Got: {r.json()}"
    )


def test_propose_changes_pr_open_failure_stays_retryable(
    client_with_user_role,
    use_local_git_remotes,
    local_test_lists_remotes,
    tmp_path,
    monkeypatch,
):
    """If opening the PR on GitHub fails (e.g. a transient outage) right
    after the branch has already been pushed, propose_changes() must
    report a real error (not a fake HTTP 200 with an empty pr_id - which
    the frontend would otherwise treat as success and render a link to
    nowhere while state silently stayed IN_PROGRESS) and must NOT advance
    state to PR_OPEN, since no PR actually exists yet. A plain retry once
    GitHub is back up must succeed normally and open a real PR containing
    the change that was already pushed.
    """
    account_id = "0" * 16
    branch = f"user-contribution/{account_id}"

    calls = {"n": 0}

    def flaky_post(apiurl, auth=None, json=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("simulated GitHub outage")
        return type("Resp", (), {
            "status_code": 200,
            "json": staticmethod(lambda: {
                "state": "open",
                "url": "https://api.github.com/repos/citizenlab/test-lists/pulls/1",
            }),
        })()

    def fake_get(url, auth=None, **kw):
        # Not mocking this made get_state()'s final check below hit the
        # real github.com and get back a genuine 404 (no "state" key),
        # which _is_pr_resolved() now correctly turns into
        # InvalidPullRequestState - masking the actual thing this test is
        # checking. Report the PR as still open so the state check reads
        # through cleanly.
        return type("Resp", (), {
            "status_code": 200,
            "json": staticmethod(lambda: {"state": "open", "url": url}),
        })()

    monkeypatch.setattr(testlists.manager.requests, "post", flaky_post)
    monkeypatch.setattr(testlists.manager.requests, "get", fake_get)

    url = "https://survives-pr-open-failure.org/"
    add_url(client_with_user_role, url, tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 400, r.json()
    assert b"err_cannot_propose_changes" in r.content
    assert get_state(client_with_user_role) == "IN_PROGRESS", (
        "state must not advance to PR_OPEN when no PR actually exists"
    )

    # The push itself already succeeded before the PR-open call failed,
    # so the branch carries the change even with no PR open yet.
    pushed = _read_pushed_csv(local_test_lists_remotes, branch, "us")
    assert url in pushed

    # Retrying (GitHub back up) must succeed normally.
    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()
    assert r.json()["pr_id"], "retry must produce a real pr_id"
    assert get_state(client_with_user_role) == "PR_OPEN"


def test_sync_state_retries_worktree_cleanup_after_transient_failure(
    client_with_user_role,
    use_local_git_remotes,
    local_test_lists_remotes,
    tmp_path,
    monkeypatch,
):
    """If cleaning up a resolved PR's worktree/branch fails partway
    through (e.g. transient contention on the shared repo from another
    account's concurrent request), sync_state() must NOT advance the
    account to CLEAN. Doing so used to leave a branch permanently
    registered by dulwich as "checked out" - its worktree directory gone
    from disk, but the administrative record of it still pointing there
    - since sync_state() never revisits an account once it's already
    CLEAN. Every future submission attempt for that account would then
    fail with dulwich's "Branch ... is already checked out" ValueError,
    with no way to recover short of an operator manually running
    `git worktree prune`/`branch -D` on the server. The fix: leave state
    as-is on a failed cleanup, so the next sync_state() call (the
    frontend polls this every 10s while PR_OPEN) notices the PR is still
    resolved and retries - self-healing any transient failure.
    """
    account_id = "0" * 16
    branch = f"user-contribution/{account_id}"

    # Custom PR mocks: GET always reports the PR as resolved (closed),
    # so sync_state() reaches the cleanup branch on every call, without
    # needing to actually merge anything via _simulate_maintainer_merge.
    def fake_post(apiurl, auth=None, json=None, **kw):
        return type("Resp", (), {
            "status_code": 200,
            "json": staticmethod(lambda: {
                "state": "open",
                "url": "https://api.github.com/repos/citizenlab/test-lists/pulls/1",
            }),
        })()

    def fake_get(url, auth=None, **kw):
        return type("Resp", (), {
            "status_code": 200,
            "json": staticmethod(lambda: {"state": "closed", "url": url}),
        })()

    monkeypatch.setattr(testlists.manager.requests, "post", fake_post)
    monkeypatch.setattr(testlists.manager.requests, "get", fake_get)

    url = "https://cleanup-retry.org/"
    add_url(client_with_user_role, url, tmp_path)
    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()

    # Make the branch-delete step of the cleanup fail on the first two
    # attempts. This must be installed BEFORE the first state check below:
    # fake_get already reports the PR as resolved, so the very next
    # get_state() call is what triggers sync_state()'s cleanup attempt -
    # installing this patch any later would let that first cleanup succeed
    # for real, leaving nothing to retry.
    #
    # Two failures, not one: the /test-list/{cc} endpoint (admin.py) calls
    # sync_state() TWICE per request - once directly (whose return value
    # becomes the response's "state" field) and again inside
    # get_test_list(). A single get_state() HTTP call therefore drives two
    # branch_delete attempts. Failing only the first left the second one
    # (still within that same request) free to succeed for real and
    # delete the branch, while the response kept reporting the first
    # call's stale "PR_OPEN" - the cleanup had actually already completed
    # underneath by the time the response was built.
    real_branch_delete = testlists.manager.git.branch_delete
    calls = {"n": 0}

    def flaky_branch_delete(repo, bname):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("simulated transient failure")
        return real_branch_delete(repo, bname)

    monkeypatch.setattr(testlists.manager.git, "branch_delete", flaky_branch_delete)

    user_worktree = Path(tmp_path) / "users" / account_id / "test-lists"
    assert user_worktree.exists()

    # First sync: cleanup fails partway through (rmtree succeeds,
    # branch_delete raises). State must stay PR_OPEN, not CLEAN.
    assert get_state(client_with_user_role) == "PR_OPEN"
    assert not user_worktree.exists(), (
        "rmtree runs before branch_delete, so the worktree dir is "
        "already gone even though the failed cleanup left state PR_OPEN"
    )
    with dulwich_git.Repo(str(Path(tmp_path) / "test-lists")) as shared_repo:
        assert branch.encode() in dulwich_git.branch_list(shared_repo), (
            "the branch must still be registered since branch_delete "
            "never completed"
        )

    # Second sync (retry): branch_delete succeeds this time. State must
    # now correctly advance to CLEAN, and the branch must actually be
    # gone - not just the directory.
    assert get_state(client_with_user_role) == "CLEAN"
    with dulwich_git.Repo(str(Path(tmp_path) / "test-lists")) as shared_repo:
        assert branch.encode() not in dulwich_git.branch_list(shared_repo)

    # This is the actual regression check: before the fix, this next
    # submission would fail with dulwich's "Branch ... is already
    # checked out" ValueError, because the earlier failed cleanup had
    # already been (incorrectly) marked CLEAN and never retried.
    url_fresh = "https://after-cleanup-retry.org/"
    add_url(client_with_user_role, url_fresh, tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"


def test_close_pr_failure_raises_and_preserves_pr_open_state(
    client_with_user_role,
    use_local_git_remotes,
    local_test_lists_remotes,
    tmp_path,
    monkeypatch,
):
    """If closing an existing PR fails (e.g. it was already merged or
    closed upstream between the last state check and now - a real race
    the code's own comments call out), update() must raise
    CannotClosePR and leave state exactly as PR_OPEN, not partially
    transition to IN_PROGRESS. This path previously had zero test
    coverage: _close_pr()'s failure signal was a bare `assert
    r.status_code == 200`, which update() only caught by relying on that
    assert raising AssertionError - a check that silently vanishes under
    `python -O`.
    """

    def fake_post(apiurl, auth=None, json=None, **kw):
        return type("Resp", (), {
            "status_code": 200,
            "json": staticmethod(lambda: {
                "state": "open",
                "url": "https://api.github.com/repos/citizenlab/test-lists/pulls/1",
            }),
        })()

    def fake_patch_fail(url, json=None, auth=None, **kw):
        return type("Resp", (), {
            "status_code": 404,
            "json": staticmethod(lambda: {"message": "Not Found"}),
        })()

    def fake_get(url, auth=None, **kw):
        # Without this, the get_state() check below hits the real
        # github.com and gets back a genuine 404, which _is_pr_resolved()
        # now correctly turns into InvalidPullRequestState instead of the
        # PR-close failure this test is actually checking.
        return type("Resp", (), {
            "status_code": 200,
            "json": staticmethod(lambda: {"state": "open", "url": url}),
        })()

    monkeypatch.setattr(testlists.manager.requests, "post", fake_post)
    monkeypatch.setattr(testlists.manager.requests, "patch", fake_patch_fail)
    monkeypatch.setattr(testlists.manager.requests, "get", fake_get)

    url_a = "https://close-pr-failure-a.org/"
    add_url(client_with_user_role, url_a, tmp_path)
    r = client_with_user_role.post("/api/v1/url-submission/submit")
    assert r.status_code == 200, r.json()
    assert get_state(client_with_user_role) == "PR_OPEN"

    d = dict(
        country_code="US",
        new_entry={
            "url": "https://close-pr-failure-b.org/",
            "category_code": "FILE",
            "date_added": "2017-04-12",
            "source": "",
            "notes": "B",
        },
        comment="add B while PR close is broken",
    )
    r = client_with_user_role.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 400, r.json()
    assert b"err_cannot_close_pr" in r.content
    assert get_state(client_with_user_role) == "PR_OPEN", (
        "a failed PR-close must leave state exactly as PR_OPEN, not "
        "partially advance to IN_PROGRESS"
    )


def test_account_isolation_uncommitted_changes_dont_leak_to_other_accounts(
    client,
    use_local_git_remotes,
    local_test_lists_remotes,
    tmp_path,
):
    """One account's in-progress (uncommitted-to-master) submission must
    be fully isolated in its own worktree/branch: it must never be
    visible to another account reading the shared list. There is also no
    request parameter anywhere that lets a caller name a different
    account_id than the one baked into their own JWT - the only way to
    touch an account's data is to hold that account's token - so this
    also checks that smuggling an account_id into the request body is
    simply ignored rather than acted upon.
    """
    account_a = "2" * 16
    account_b = "3" * 16
    headers_a = {"Authorization": f"Bearer {create_session_token(account_a, 'user')}"}
    headers_b = {"Authorization": f"Bearer {create_session_token(account_b, 'user')}"}

    def add(headers, url):
        d = dict(
            country_code="US",
            new_entry={
                "url": url,
                "category_code": "FILE",
                "date_added": "2017-04-12",
                "source": "",
                "notes": "isolation test",
            },
            comment=f"add {url}",
        )
        r = client.post("/api/v1/url-submission/update-url", json=d, headers=headers)
        assert r.status_code == 200, r.json()

    def get_list(headers, cc="us"):
        r = client.get(f"/api/_/url-submission/test-list/{cc}", headers=headers)
        assert r.status_code == 200, r.json()
        body = r.json()
        return body["test_list"], body["state"]

    # B starts clean, unaffected by anything A is about to do.
    tl_b_before, state_b_before = get_list(headers_b)
    assert state_b_before == "CLEAN"

    url_a = "https://isolated-to-account-a.org/"
    add(headers_a, url_a)

    tl_a, state_a = get_list(headers_a)
    assert state_a == "IN_PROGRESS"
    assert any(e["url"] == url_a for e in tl_a)

    # B's view must be completely unaffected by A's still-uncommitted
    # change - not in B's list, and B's own state untouched.
    tl_b_after, state_b_after = get_list(headers_b)
    assert state_b_after == "CLEAN"
    assert not any(e["url"] == url_a for e in tl_b_after)
    assert len(tl_b_after) == len(tl_b_before)

    # Smuggling an account_id into the request body (not part of the
    # schema at all) must be silently ignored, not acted upon.
    spoof_url = "https://spoof-attempt.org/"
    r = client.post(
        "/api/v1/url-submission/update-url",
        json=dict(
            country_code="US",
            account_id=account_b,
            new_entry={
                "url": spoof_url,
                "category_code": "FILE",
                "date_added": "2017-04-12",
                "source": "",
                "notes": "spoof",
            },
            comment="attempt to act as another account",
        ),
        headers=headers_a,
    )
    assert r.status_code == 200, r.json()

    tl_b_final, _ = get_list(headers_b)
    assert not any(e["url"] == spoof_url for e in tl_b_final), (
        "a smuggled account_id in the request body must be ignored; the "
        "edit must land on the caller's own (A's) worktree, never B's"
    )
    tl_a_final, _ = get_list(headers_a)
    assert any(e["url"] == spoof_url for e in tl_a_final)


def test_second_users_branch_misses_first_users_merged_change(
    client,
    use_local_git_remotes,
    local_test_lists_remotes,
    tmp_path,
    monkeypatch,
):
    """Documents a known limitation, not a regression: URLListManager
    never rebases a user's long-lived worktree branch onto the latest
    origin master before pushing.

    Scenario: user A submits and their PR gets merged. User B has their
    own in-progress submission whose worktree/branch was cut *before* A's
    merge, adds more changes to it, and only then submits. Because the
    service never updates B's branch against the new master in between,
    B's pushed branch is missing A's already-merged change even though
    it's sitting right there on master - exactly the kind of drift that
    turns into a real merge conflict (or a silent, wrong resolution) once
    a human tries to merge B's PR too. Rebasing (or at least fast-forward
    merging) each user's branch onto origin's current master before
    pushing would avoid this class of problem; this test exists to make
    the current behavior visible and catch it if it silently changes.

    It then goes on to merge B's PR too, and checks the normal case still
    works end-to-end: B's state goes back to CLEAN, their worktree/branch
    get pruned, and a fresh submission afterwards - now cut from a master
    that already has both A's and B's changes - works cleanly and with no
    drift, in contrast to the stale-branch case above.
    """
    account_a = "0" * 16
    account_b = "1" * 16
    branch_a = f"user-contribution/{account_a}"
    branch_b = f"user-contribution/{account_b}"
    headers_a = {"Authorization": f"Bearer {create_session_token(account_a, 'user')}"}
    headers_b = {"Authorization": f"Bearer {create_session_token(account_b, 'user')}"}

    # Fake PR API: every POST gets back a globally-unique PR URL, exactly
    # like real GitHub hands out a fresh, incrementing PR number for every
    # new pull request. GET/PATCH are resolved by that exact URL via
    # resolved_prs.
    #
    # An earlier version of this mock derived the fake PR URL solely from
    # the account_id (so it could tell A's PR apart from B's), which is
    # exactly what breaks below: once B's first PR is merged and later B
    # opens a *second* PR, an account-keyed URL can't tell that new PR
    # apart from the already-merged one, so sync_state() immediately (and
    # incorrectly) reported the brand new PR as resolved too. Keying by a
    # counter instead of the account fixes this the same way GitHub itself
    # avoids the ambiguity - by never reusing a PR's identity.
    pr_counter = {"n": 0}
    resolved_prs = set()

    def fake_post(apiurl, auth=None, json=None, **kw):
        pr_counter["n"] += 1
        url = f"https://api.github.com/repos/citizenlab/test-lists/pulls/{pr_counter['n']}"
        return type("Resp", (), {
            "status_code": 200,
            "json": staticmethod(lambda: {"state": "open", "url": url}),
        })()

    def fake_patch(url, json=None, auth=None, **kw):
        return type("Resp", (), {
            "status_code": 200,
            "json": staticmethod(lambda: {"state": "closed", "url": url}),
        })()

    def fake_get(url, auth=None, **kw):
        pr_state = "closed" if url in resolved_prs else "open"
        return type("Resp", (), {
            "status_code": 200,
            "json": staticmethod(lambda: {"state": pr_state, "url": url}),
        })()

    monkeypatch.setattr(testlists.manager.requests, "post", fake_post)
    monkeypatch.setattr(testlists.manager.requests, "patch", fake_patch)
    monkeypatch.setattr(testlists.manager.requests, "get", fake_get)

    def add(headers, url, notes):
        d = dict(
            country_code="US",
            new_entry={
                "url": url,
                "category_code": "FILE",
                "date_added": "2017-04-12",
                "source": "",
                "notes": notes,
            },
            comment=f"add {url}",
        )
        r = client.post("/api/v1/url-submission/update-url", json=d, headers=headers)
        assert r.status_code == 200, r.json()

    def state(headers, cc="ie"):
        r = client.get(f"/api/_/url-submission/test-list/{cc}", headers=headers)
        assert r.status_code == 200, r.json()
        return r.json()["state"]

    def submit(headers):
        r = client.post("/api/v1/url-submission/submit", headers=headers)
        assert r.status_code == 200, r.json()
        return r.json()["pr_id"]

    def merge_and_resolve(account_id, branch):
        # Simulate a human accepting and merging the PR on GitHub. A's PR
        # merges as a clean fast-forward (master hasn't moved since A's
        # branch was cut), but B's can't: master has since moved (A's
        # change landed) and B's branch never picked that up, so a plain
        # force-push would silently discard A's already-merged change
        # instead of merging. _simulate_maintainer_merge() handles both
        # cases correctly via a real (if manually-applied) content merge,
        # matching what an actual GitHub merge would produce either way.
        _simulate_maintainer_merge(
            local_test_lists_remotes["origin"],
            local_test_lists_remotes["push"],
            branch,
            cc="us",
        )
        # Mark this account's *current* PR - and only that specific PR,
        # by its exact URL - as merged/resolved, by reading the URL the
        # service itself just persisted to disk. This is what lets a
        # later, brand new PR for the same account still be correctly
        # seen as open (see the fake_get/pr_counter comment above).
        pr_id_path = Path(tmp_path) / "users" / account_id / "pr_id"
        resolved_prs.add(pr_id_path.read_text())

    # --- User A creates and submits their change first.
    assert state(headers_a) == "CLEAN"
    url_a = "https://user-a-first.org/"
    add(headers_a, url_a, "A")
    assert state(headers_a) == "IN_PROGRESS"
    submit(headers_a)
    assert state(headers_a) == "PR_OPEN"

    # --- User B starts their own in-progress submission. B's worktree is
    # cut from master as it stands *right now* - before A's PR is merged.
    assert state(headers_b) == "CLEAN"
    url_b1 = "https://user-b-first.org/"
    add(headers_b, url_b1, "B1")
    assert state(headers_b) == "IN_PROGRESS"

    # --- A's PR is accepted and merged into origin's master.
    merge_and_resolve(account_a, branch_a)

    # A GET for account A makes sync_state() notice the PR is resolved and
    # clean up A's worktree/branch - the normal post-merge cleanup path.
    assert state(headers_a) == "CLEAN"

    # --- User B adds MORE changes to their still-open submission *after*
    # A's change has already landed on master, then finally submits. B's
    # own PR isn't resolved yet, so this must stay PR_OPEN, not CLEAN.
    url_b2 = "https://user-b-second.org/"
    add(headers_b, url_b2, "B2")
    assert state(headers_b) == "IN_PROGRESS"
    submit(headers_b)
    assert state(headers_b) == "PR_OPEN"

    # Sanity check: A's change really is on origin's master by now.
    master_content = _read_csv_from_repo(
        local_test_lists_remotes["origin"], "master", "us"
    )
    assert url_a in master_content

    # This is the known issue: B's branch never picked up A's change, even
    # though B added more to their submission and submitted well after
    # A's PR merged. If a human merged B's PR as-is, the result depends on
    # exactly where in the file each line landed - best case, git resolves
    # it automatically; worst case, it's a conflict a maintainer has to
    # untangle by hand. Rebasing B's branch onto master before this push
    # would have avoided the question entirely.
    pushed_b = _read_pushed_csv(local_test_lists_remotes, branch_b, "us")
    assert url_b1 in pushed_b
    assert url_b2 in pushed_b
    assert url_a not in pushed_b, (
        "expected B's branch to still be missing A's merged change "
        "(documents the known stale-base/needs-rebase limitation); if "
        "this now fails because url_a IS present, someone has added "
        "rebase-onto-master behavior and this test should be updated "
        "to assert the fixed behavior instead"
    )

    # --- Now B's PR *also* gets accepted and merged (a maintainer might
    # do this even with the drift above - CSVs with additions in
    # different places often merge cleanly by hand, or the maintainer
    # just resolves the trivial conflict). Check the normal cleanup path
    # still works correctly for B, same as it did for A.
    merge_and_resolve(account_b, branch_b)

    assert state(headers_b) == "CLEAN"

    user_b_worktree = Path(tmp_path) / "users" / account_b / "test-lists"
    assert not user_b_worktree.exists(), (
        "B's worktree should have been removed by sync_state()'s cleanup"
    )
    with dulwich_git.Repo(str(Path(tmp_path) / "test-lists")) as shared_repo:
        remaining_branches = dulwich_git.branch_list(shared_repo)
        assert branch_b.encode() not in remaining_branches, (
            "B's branch should have been deleted by sync_state()'s cleanup"
        )

    # --- And B's *next* submission - starting completely fresh - must
    # still work: a new worktree/branch gets created from current master,
    # which by now already has both A's and B's earlier changes on it.
    assert state(headers_b) == "CLEAN"
    url_b3 = "https://user-b-third.org/"
    add(headers_b, url_b3, "B3")
    assert state(headers_b) == "IN_PROGRESS"
    submit(headers_b)
    assert state(headers_b) == "PR_OPEN"

    # No drift this time: a fresh worktree cut from current master
    # naturally carries everything already merged, plus the new addition.
    pushed_b_fresh = _read_pushed_csv(local_test_lists_remotes, branch_b, "us")
    assert url_a in pushed_b_fresh
    assert url_b1 in pushed_b_fresh
    assert url_b2 in pushed_b_fresh
    assert url_b3 in pushed_b_fresh


def test_update_url_succeeds_without_ambient_git_identity(
    client_with_user_role,
    mock_github_pr_api,
    use_local_git_remotes,
    tmp_path,
    monkeypatch,
):
    """Regression test for the "container has no git identity" bug.

    In production this service runs as a bare numeric UID with no
    matching /etc/passwd entry (bash shows this as "I have no name!") and
    no git identity configured anywhere. dulwich's get_user_identity()
    falls through the LOGNAME/USER/LNAME/USERNAME env vars, then
    pwd.getpwuid(), and raises dulwich.errors.DefaultIdentityNotFound if
    none of those resolve - which aborted git.commit() *after* the CSV
    file had already been rewritten on disk by tmp_f.rename(csv_f),
    silently leaving the branch stuck on the old commit. manager.update()
    now passes an explicit author=/committer= to git.commit(), so it no
    longer depends on any of this.

    NOTE: this test is scoped narrowly to that one call. Cloning the repo
    and creating the user's worktree/branch for the first time *also* need
    a resolvable identity (see use_local_git_remotes's docstring), but via
    a completely different dulwich code path (reflog writes) that isn't,
    and shouldn't need to be, covered by manager.py's fix - that's
    dulwich's own internal bookkeeping, not something this service's code
    controls. So the identity is wiped only *after* a first add_url()
    warms up the clone + worktree/branch creation with use_local_git_
    remotes' pinned identity still in place, isolating this test to
    exactly the claim it's making: that the actual git.commit() call in
    update() no longer depends on ambient identity.
    """
    import pwd

    assert get_state(client_with_user_role) == "CLEAN"
    add_url(client_with_user_role, "https://example-warmup.org/", tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    for name in (
        "LOGNAME",
        "USER",
        "LNAME",
        "USERNAME",
        "EMAIL",
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)

    def no_passwd_entry(uid):
        raise KeyError(f"no passwd entry for uid {uid}")

    monkeypatch.setattr(pwd, "getpwuid", no_passwd_entry)

    # The repo and the user's worktree/branch already exist from the
    # warm-up add_url() above, so this second update() only needs
    # git.pull() (a no-op fast path here, since nothing upstream changed)
    # and git.commit() - which is exactly the call this test is verifying.
    add_url(client_with_user_role, "https://example-no-identity.org/", tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"


def test_push_refuses_when_worktree_has_uncommitted_changes(
    client_with_user_role,
    mock_github_pr_api,
    use_local_git_remotes,
    tmp_path,
):
    """Regression test for the actual failure mode behind the bug report:
    a CSV edit that landed on disk in the user's worktree (via
    tmp_f.rename(csv_f) in manager.update()) but was never committed,
    because git.add() and/or git.commit() raised right after. Comparing
    refs/heads/<branch> against the worktree's HEAD can't catch this
    (HEAD is a symref into the exact same shared ref storage, so the two
    always agree); _push_to_repo() now checks the worktree's status
    instead and must refuse to push when it isn't clean.
    """
    account_id = "0" * 16

    assert get_state(client_with_user_role) == "CLEAN"
    add_url(client_with_user_role, "https://example-stale.org/", tmp_path)
    assert get_state(client_with_user_role) == "IN_PROGRESS"

    # Reproduce the bug's end state directly: edit the tracked CSV file in
    # the worktree without going through git add/commit at all.
    user_csv = (
        Path(tmp_path)
        / "users"
        / account_id
        / "test-lists"
        / "lists"
        / "us.csv"
    )
    with user_csv.open("a") as f:
        f.write(
            "https://sneaky-uncommitted-url.org/,FILE,File-sharing,"
            "2017-04-12,,Uncommitted\n"
        )

    r = client_with_user_role.post("/api/v1/url-submission/submit")
    # _push_to_repo() raises CannotUpdateList() here, which propose_changes()
    # now surfaces as CannotProposeChanges() (see manager.py) instead of
    # swallowing it into a fake 200 with an empty pr_id.
    assert r.status_code == 400, r.json()
    assert b"err_cannot_propose_changes" in r.content

    # State must not have advanced to PR_OPEN off the back of a push that
    # never actually happened.
    assert get_state(client_with_user_role) != "PR_OPEN"


def test_failed_update_releases_account_lock(
    client_with_user_role,
    use_local_git_remotes,
    tmp_path,
    monkeypatch,
):
    """Regression test for the FileLock leak this investigation also
    turned up: an exception inside ulm.update() must not leave the
    per-account FileLock held. Previously `del ulm` (+ gc.collect() in the
    submit/list endpoints) only ran on the success path, so any failure -
    including the git-identity bug above - left the lock held until an
    unrelated request elsewhere happened to force a full GC pass. Every
    other request for the same account (even plain reads) would then fail
    with filelock.Timeout for up to 5s at a time - this is exactly what
    happened in production right after a failed update-url call.
    """
    account_id = "0" * 16

    def boom(*a, **kw):
        raise RuntimeError("simulated git.commit failure")

    monkeypatch.setattr(testlists.manager.git, "commit", boom)

    d = dict(
        country_code="US",
        new_entry={
            "url": "https://example-lock-test.org/",
            "category_code": "FILE",
            "date_added": "2017-04-12",
            "source": "",
            "notes": "Integ test",
        },
        comment="Integ test: trigger commit failure",
    )
    r = client_with_user_role.post("/api/v1/url-submission/update-url", json=d)
    assert r.status_code == 400

    # The failing request above must have released the lock before
    # returning. If it didn't, this acquire will time out (default
    # timeout=5s in URLListManager.get_user_lock) instead of succeeding
    # immediately.
    lockfile = Path(tmp_path) / "users" / account_id / "state.lock"
    lock = FileLock(str(lockfile), timeout=2)
    lock.acquire()
    lock.release()

    # And a completely unrelated, ordinary request for the same account
    # must not 500 with a lock timeout either.
    r = client_with_user_role.get("/api/_/url-submission/test-list/us")
    assert r.status_code == 200


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
    #xxx = dict(category_code="NEWS", priority=100, cc='', url="INTEG-TEST") # XXX: should cc be '' ? should domain be set?
    xxx = dict(category_code="NEWS", priority=100, url="INTEG-TEST", domain="*", cc="*")
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
    # XXX: what fields are required to do an update? how is the item keyed in the database? by URL?
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
    assert r.json() == 1

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
