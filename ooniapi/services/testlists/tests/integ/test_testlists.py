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
    assert r.status_code == 200  # propose_changes() fails soft, see manager.py
    assert r.json()["pr_id"] == ""  # ...but refuses to push a dirty worktree

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
