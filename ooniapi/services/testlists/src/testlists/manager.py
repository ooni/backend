import csv
import logging
import os
import json
import re
import requests  # debdeps: python3-requests
import shutil
import time
from typing import Dict, List
from datetime import datetime
from dulwich import porcelain as git
from filelock import FileLock  # debdeps: python3-filelock
from pathlib import Path
from urllib.parse import urlparse
from requests.auth import HTTPBasicAuth
from .common.metrics import timer
from .common.errors import *


log = logging.getLogger(__name__)

BAD_CHARS = ["\r", "\n", "\t", "\\"]

VALID_URL = regex = re.compile(
    r"^(?:http)s?://"  # http:// or https://
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain...
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
    r"(?::\d+)?"  # optional port
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)

CATEGORY_CODES = {
    "ALDR": "Alcohol & Drugs",
    "REL": "Religion",
    "PORN": "Pornography",
    "PROV": "Provocative Attire",
    "POLR": "Political Criticism",
    "HUMR": "Human Rights Issues",
    "ENV": "Environment",
    "MILX": "Terrorism and Militants",
    "HATE": "Hate Speech",
    "NEWS": "News Media",
    "XED": "Sex Education",
    "PUBH": "Public Health",
    "GMB": "Gambling",
    "ANON": "Anonymization and circumvention tools",
    "DATE": "Online Dating",
    "GRP": "Social Networking",
    "LGBT": "LGBT",
    "FILE": "File-sharing",
    "HACK": "Hacking Tools",
    "COMT": "Communication Tools",
    "MMED": "Media sharing",
    "HOST": "Hosting and Blogging Platforms",
    "SRCH": "Search Engines",
    "GAME": "Gaming",
    "CULTR": "Culture",
    "ECON": "Economics",
    "GOVT": "Government",
    "COMM": "E-commerce",
    "CTRL": "Control content",
    "IGO": "Intergovernmental Organizations",
    "MISC": "Miscelaneous content",
}

CITIZENLAB_CSV_HEADER = (
    "url",
    "category_code",
    "category_description",
    "date_added",
    "source",
    "notes",
)


def _read_ref(repo, ref_name: str):
    """Read a ref's sha, returning None instead of raising if it doesn't
    exist yet (e.g. before the first commit on a brand new branch)."""
    try:
        return repo.refs[ref_name.encode()]
    except KeyError:
        return None


def check_url(url):
    if not VALID_URL.match(url):
        raise BadURL()
    elif any([c in url for c in BAD_CHARS]):
        raise BadURL()
    elif url != url.strip():
        raise BadURL()
    elif urlparse(url).path == "":
        raise BadURL()


def validate_entry(entry: Dict[str, str]) -> None:
    keys = ["category_code", "date_added", "notes", "source", "url"]
    if sorted(entry.keys()) != keys:
        raise Exception(f"Incorrect entry keys {list(entry)}")

    check_url(entry["url"])
    if entry["category_code"] not in CATEGORY_CODES:
        raise BadCategoryCode()

    try:
        date_added = entry["date_added"]
        d = datetime.strptime(date_added, "%Y-%m-%d").date().isoformat()
        if d != date_added:
            raise BadDate()
    except Exception:
        raise BadDate()


def get_url_list_manager(settings, account_id):
    return URLListManager(
        working_dir=Path(settings.working_dir),
        github_user=settings.github_user,
        github_token=settings.github_token,
        origin_repo=settings.origin_repo,
        push_repo=settings.push_repo,
        account_id=account_id,
    )

class URLListManager:
    def __init__(
        self, working_dir, github_user, github_token, push_repo, origin_repo, account_id
    ):
        self.working_dir = working_dir
        self.origin_repo = origin_repo
        self.push_repo = push_repo
        self.github_user = github_user
        self.github_token = github_token
        self.repo_dir = self.working_dir / "test-lists"
        self.push_username = push_repo.split("/")[0]
        # lock before init repo
        self.get_user_lock(account_id)
        try:
            self._init_repo()
        except Exception:
            # _init_repo() does real network I/O (git.clone/git.pull
            # against github.com). If it raises, this constructor raises
            # too, so get_url_list_manager() never returns an object -
            # callers' `ulm = None; try: ulm = get_url_list_manager(...)
            # ... finally: if ulm is not None: ulm.close()` pattern can
            # never call close() on something that was never assigned,
            # even though the lock above was already acquired. Without
            # this, the lock would only be released whenever __del__
            # happens to run via GC - exactly the delayed-release problem
            # close() exists to eliminate, just reachable through a
            # network hiccup during clone/pull instead of a git.commit()
            # failure.
            self.close()
            raise

    def get_user_lock(self, account_id: str):
        lockfile_dir = self.working_dir / "users" / account_id
        lockfile_f = lockfile_dir / "state.lock"
        lockfile_dir.mkdir(parents=True, exist_ok=True)  # no race cond. here
        self._lock_time = time.monotonic_ns()
        self._lock = FileLock(lockfile_f, timeout=5, thread_local=False)
        self._lock.acquire()  # released on URLListManager destruction

    def close(self):
        """Explicitly release the per-account FileLock.

        This is idempotent and safe to call multiple times (including when
        the lock was never successfully acquired, e.g. because __init__
        raised a filelock.Timeout before get_user_lock() finished).

        Callers MUST call this from a try/finally around any use of a
        URLListManager rather than relying on __del__/gc to release the
        lock. In production, an exception raised out of ulm.update() (or
        similar) with only a bare `del ulm` on the success path left the
        object - and its held FileLock - alive for as long as the
        exception's traceback was referenced (which can be far longer than
        the request that created it, since tracebacks keep local frames,
        including `ulm`, alive). Every subsequent request for that same
        account_id then hit a filelock.Timeout of its own (observed in
        production as cascading 500s on unrelated read-only endpoints)
        until some unrelated request elsewhere happened to force a full GC
        pass.
        """
        lock = getattr(self, "_lock", None)
        if lock is not None and lock.is_locked:
            elapsed_ms = (time.monotonic_ns() - self._lock_time) / 1000_000
            log.debug(f"[git-debug] releasing lock {lock.lock_file} held for {elapsed_ms}ms")
            lock.release()

    @timer(name="citizenlab_lock_time")
    def __del__(self):
        # Fallback safety net only - close() should already have been
        # called explicitly via try/finally by every caller. Do NOT raise
        # here: exceptions raised inside __del__ are silently discarded by
        # Python anyway (just printed as noisy "Exception ignored in..."
        # lines), and "the lock isn't held anymore/never was" is an
        # entirely expected state to find here (e.g. close() already ran,
        # or __init__ never got past get_user_lock()).
        try:
            self.close()
        except Exception:
            log.exception("[git-debug] error releasing lock in URLListManager.__del__")

    @timer(name="citizenlab_repo_init")
    def _init_repo(self):
        if not os.path.exists(self.repo_dir):
            log.info(f"Cloning {self.origin_repo} repository")
            url = f"https://github.com/{self.origin_repo}.git"
            git.clone(url, self.repo_dir, branch="master")

            # Create a remote for push access
            log.info(f"Adding {self.push_repo} repository")
            remote_url = f"https://{self.github_user}:{self.github_token}@github.com/{self.push_repo}.git"
            git.remote_add(self.repo_dir, "rworigin", remote_url)

        # Pull the latest changes
        repo = git.Repo(self.repo_dir)
        git.pull(repo, 'origin', 'master')

    def _get_user_repo_path(self, account_id) -> Path:
        return self.working_dir / "users" / account_id / "test-lists"

    def _get_user_statefile_path(self, account_id) -> Path:
        return self.working_dir / "users" / account_id / "state"

    def _get_user_pr_path(self, account_id) -> Path:
        return self.working_dir / "users" / account_id / "pr_id"

    def _get_user_changes_path(self, account_id) -> Path:
        return self.working_dir / "users" / account_id / "changes.pickle"

    def _get_user_branchname(self, account_id: str) -> str:
        return f"user-contribution/{account_id}"

    def get_state(self, account_id: str):
        """
        Returns the current state of the repo for the given user.

        The possible states are:
        - CLEAN:
            when we are in sync with the current tip of master and no changes
            have been made
        - IN_PROGRESS:
            when there are some changes in the working tree of the user, but
            they haven't yet pushed them
        - PR_OPEN:
            when the PR of the user is open on github and it's waiting for
            being merged
        """
        try:
            return self._get_user_statefile_path(account_id).read_text()
        except FileNotFoundError:
            return "CLEAN"

    def _set_state(self, account_id, state: str):
        """
        This will record the current state of the pull request for the user to
        the statefile.
        The absence of a statefile is an indication of a clean state.
        """
        assert state in ("IN_PROGRESS", "PR_OPEN", "CLEAN"), "Unexpected state"
        log.debug(f"setting state for {account_id} to {state}")
        if state == "CLEAN":
            self._get_user_statefile_path(account_id).unlink()
            self._get_user_pr_path(account_id).unlink()
            return

        with open(self._get_user_statefile_path(account_id), "w") as out_file:
            out_file.write(state)

    def _set_pr_id(self, account_id: str, pr_id):
        self._get_user_pr_path(account_id).write_text(pr_id)

    def _get_pr_id(self, account_id: str):
        """Returns an API URL e.g.
        https://api.github.com/repos/citizenlab/test-lists/pulls/800
        Raises if the PR was never opened
        """
        return self._get_user_pr_path(account_id).read_text()

    def get_pr_url(self, account_id: str):
        """Returns a browsable URL
        Raises if the PR was never opened
        """
        apiurl = self._get_pr_id(account_id)
        pr_num = apiurl.split("/")[-1]
        return f"https://github.com/{self.origin_repo}/pull/{pr_num}"

    def _get_user_repo(self, account_id: str):
        repo_path = self._get_user_repo_path(account_id)
        if not os.path.exists(repo_path):
            log.info(f"creating {repo_path}")
            with git.Repo(self.repo_dir) as repo:
                git.worktree_add(repo, path=repo_path, branch=self._get_user_branchname(account_id))
        return git.Repo(repo_path)

    def get_test_list(self, account_id, country_code) -> List[Dict[str, str]]:
        country_code = country_code.lower()
        if len(country_code) != 2 and country_code != "global":
            raise InvalidCountryCode()

        self.sync_state(account_id)
        self._pull_origin_repo()

        repo_path = self._get_user_repo_path(account_id)
        if not os.path.exists(repo_path):
            repo_path = self.repo_dir

        path = repo_path / "lists" / f"{country_code}.csv"
        log.debug(f"Reading {path}")
        keys = set(("url", "category_code", "date_added", "source", "notes"))
        tl = []
        try:
            with path.open() as tl_file:
                reader = csv.DictReader(tl_file)
                for e in reader:
                    d = {k: (e[k] or "") for k in keys}
                    tl.append(d)

            return tl
        except FileNotFoundError:
            raise CountryNotSupported()

    def _prevent_duplicate_url(self, account_id, country_code, new_url):
        rows = self.get_test_list(account_id, country_code)
        if country_code != "global":
            rows.extend(self.get_test_list(account_id, "global"))

        if new_url in (r["url"] for r in rows):
            raise DuplicateURLError(
                description=f"{new_url} is duplicate", err_args={"url": new_url}
            )

    @timer(name="citizenlab_repo_pull")
    def _pull_origin_repo(self):
        with git.Repo(self.repo_dir) as repo:
            git.pull(repo, 'origin', 'master')

    @timer(name="citizenlab_sync_state")
    def sync_state(self, account_id) -> str:
        state = self.get_state(account_id)
        if state in ("CLEAN", "IN_PROGRESS"):
            # we don't have to do anything
            return state

        if self._is_pr_resolved(account_id):
            path = self._get_user_repo_path(account_id)
            bname = self._get_user_branchname(account_id)
            log.debug(f"Deleting {path}")
            try:
                try:
                    shutil.rmtree(path)
                except FileNotFoundError:
                    pass
                with git.Repo(self.repo_dir) as repo:
                    git.worktree_prune(repo)
                    git.branch_delete(repo, bname)
                self._maybe_delete_changes_log(account_id)
            except Exception:
                # NOTE: this used to unconditionally set state=CLEAN below
                # even when cleanup failed partway through (e.g. rmtree
                # succeeded but branch_delete didn't). Since sync_state()
                # never revisits an account once it's CLEAN, that
                # permanently registered the branch as "checked out" in
                # dulwich's administrative records - the next
                # worktree_add() for this account would raise ValueError
                # forever, with no way to recover short of an operator
                # manually running `git worktree prune`/`branch -D`.
                # Leaving state as-is instead makes this self-healing: the
                # frontend polls sync_state() every 10s while PR_OPEN, so a
                # transient failure just gets retried on the next call.
                log.exception(
                    f"[git-debug] account={account_id} failed to clean "
                    f"up worktree/branch {bname} after PR merge - "
                    "leaving state as-is so this is retried on the next "
                    "sync rather than getting stuck"
                )
                return state

            self._set_state(account_id, "CLEAN")
            state = "CLEAN"

        return state

    def _maybe_delete_changes_log(self, account_id):
        changes_log = self._get_user_changes_path(account_id)
        try:
            changes_log.unlink()
        except FileNotFoundError:
            pass

    def read_changes_log(self, account_id):
        changes_log = self._get_user_changes_path(account_id)
        try:
            with changes_log.open("rb") as in_file:
                return json.load(in_file)
        except FileNotFoundError:
            return {}

    def write_changes_log(
        self, account_id: str, cc: str, old_entry: dict, new_entry: dict
    ):
        changeset = self.read_changes_log(account_id)
        cc_changeset = changeset.setdefault(cc, [])

        if old_entry:
            try:
                changeset[cc].remove(dict(old_entry, **{"action": "add"}))
            except ValueError:
                # Not part of the changeset, no problem
                pass

        if new_entry:
            # We check if the new_entry we are adding had previously been
            # deleted. In this case it needs to removed from the log.
            try:
                changeset[cc].remove(dict(new_entry, **{"action": "delete"}))
            except ValueError:
                pass

            changeset[cc].append(dict(new_entry, **{"action": "add"}))

        elif old_entry:
            changeset[cc].append(dict(old_entry, **{"action": "delete"}))

        with self._get_user_changes_path(account_id).open("w") as out_file:
            json.dump(changeset, out_file)

    def update(
        self, account_id: str, cc: str, old_entry: dict, new_entry: dict, comment: str
    ):
        """
        Create/update/delete test list entries.
        """
        # TODO: set date_added to now() on new_entry
        # fields follow the order in the CSV files
        # NOTE: these were bare asserts, which `python -O`/PYTHONOPTIMIZE
        # strips entirely - silently skipping validation of data (an HTTP
        # request body) that isn't guaranteed to have the expected shape.
        if old_entry:
            old_entry["category_description"] = CATEGORY_CODES[
                old_entry["category_code"]
            ]
            if sorted(old_entry.keys()) != sorted(CITIZENLAB_CSV_HEADER):
                raise InvalidRequest(description="old_entry has unexpected keys")

        if new_entry:
            new_entry["category_description"] = CATEGORY_CODES[
                new_entry["category_code"]
            ]
            if sorted(new_entry.keys()) != sorted(CITIZENLAB_CSV_HEADER):
                raise InvalidRequest(description="new_entry has unexpected keys")

        if old_entry and new_entry:
            log.debug("updating existing entry")
        elif old_entry:
            log.debug("deleting existing entry")
        elif new_entry:
            log.debug("creating new entry")

        cc = cc.lower()
        if len(cc) != 2 and cc != "global":
            raise InvalidCountryCode()

        if old_entry == new_entry:
            raise NoProposedChanges()

        self._pull_origin_repo()
        self.sync_state(account_id)
        state = self.get_state(account_id)

        # When the PR is open and we are performing an CUD operation, we need
        # to first close to pull request and restore the state of the users
        # branch to IN_PROGRESS.
        # Changes are not pushed directly to the branch, because that increases
        # the change of github reviewers from merging the PR while the user is
        # still making changes.
        # Effectively the PR being openned acts as a lock on the changes for
        # the user, once the PR is open the lock is acquired, when the PR is
        # closed, it's released.
        if state in ("PR_OPEN"):
            # _close_pr() now raises CannotClosePR() directly on failure
            # (including the race where the PR was already merged/closed
            # upstream between our last check and now) instead of relying
            # on us catching an AssertionError from a bare assert.
            self._close_pr(account_id)
            self._set_state(account_id, "IN_PROGRESS")

        with self._get_user_repo(account_id) as repo:
            csv_f = self._get_user_repo_path(account_id) / "lists" / f"{cc}.csv"
            tmp_f = csv_f.with_suffix(".tmp")

            if new_entry:
                # Check for collisions:
                if not old_entry:
                    self._prevent_duplicate_url(account_id, cc, new_entry["url"])

                elif old_entry and new_entry["url"] != old_entry["url"]:
                    # If the URL is being changed check for collisions
                    self._prevent_duplicate_url(account_id, cc, new_entry["url"])

            with csv_f.open() as in_f, tmp_f.open("w") as out_f:
                reader = csv.DictReader(in_f)
                writer = csv.DictWriter(
                    out_f,
                    quoting=csv.QUOTE_MINIMAL,
                    lineterminator="\n",
                    fieldnames=CITIZENLAB_CSV_HEADER,
                )
                writer.writeheader()

                done = False
                for row in reader:
                    if row == old_entry:
                        if new_entry:
                            writer.writerow(new_entry)  # update entry
                        else:
                            pass  # delete entry
                        done = True

                    else:
                        writer.writerow(row)

                if new_entry and not old_entry:
                    writer.writerow(new_entry)  # add new entry at end
                    done = True

            if not done:
                tmp_f.unlink()
                raise CannotUpdateList()

            log.debug(f"Writing {csv_f.as_posix()}")
            tmp_f.rename(csv_f)

            # NOTE: from here on the working tree file has already been
            # updated on disk. If anything below raises, the CSV change is
            # visible in the user's worktree but was never committed, so the
            # branch ref keeps pointing at the old commit. The next push will
            # then push a branch that is missing this change even though the
            # file on disk looks up to date. Capture full context + traceback
            # around dulwich calls so this can no longer fail silently.
            try:
                branch_name = self._get_user_branchname(account_id)
                old_head = _read_ref(repo, f"refs/heads/{branch_name}")
                log.debug(
                    f"[git-debug] account={account_id} cc={cc} repo_path={repo.path} "
                    f"branch={branch_name} old_head={old_head}"
                )

                added, ignored = git.add(repo=repo, paths=[csv_f.as_posix()])
                log.debug(
                    f"[git-debug] account={account_id} git.add added={added} "
                    f"ignored={ignored}"
                )

                # Explicitly set the committer/author identity instead of
                # relying on dulwich's system-derived fallback
                # (user.name/email from git config, then GIT_COMMITTER_*
                # env vars, then the OS user/gecos/hostname). In a
                # container that has no git identity configured this
                # fallback can be missing/malformed and dulwich raises
                # InvalidUserIdentity from check_user_identity(), which
                # would abort the commit *after* the file has already been
                # renamed into place above.
                bot_identity = f"{self.github_user} <{self.github_user}@users.noreply.github.com>".encode()

                new_head = git.commit(
                    repo,
                    message=comment,
                    author=bot_identity,
                    committer=bot_identity,
                )
                log.debug(
                    f"[git-debug] account={account_id} git.commit new_head={new_head}"
                )

                # Defensive check: make sure the branch ref actually moved.
                # If dulwich raised inside commit() *after* updating the ref
                # (e.g. during hook execution or auto-gc) this would still
                # be fine; but if for any reason the ref wasn't updated we
                # want to know loudly rather than silently push a stale
                # branch later.
                current_head = _read_ref(repo, f"refs/heads/{branch_name}")
                if current_head != new_head:
                    log.error(
                        f"[git-debug] account={account_id} branch {branch_name} "
                        f"ref is {current_head!r} but expected commit {new_head!r} "
                        "- branch was NOT updated by git.commit()"
                    )
                    raise CannotUpdateList(
                        description="Failed to update branch after commit"
                    )
            except Exception:
                log.exception(
                    f"[git-debug] account={account_id} cc={cc} "
                    f"csv_f={csv_f.as_posix()} repo_path={repo.path} "
                    "git add/commit failed - worktree file was already "
                    "written to disk but the commit/branch update did not "
                    "complete"
                )
                raise

            self.write_changes_log(account_id, cc, old_entry, new_entry)

            self._set_state(account_id, "IN_PROGRESS")

    @timer(name="citizenlab_open_pr")
    def _open_pr(self, branchname):
        """Opens PR. Returns API URL e.g.
        https://api.github.com/repos/citizenlab/test-lists/pulls/800
        """
        head = f"{self.push_username}:{branchname}"
        log.info(
            f"opening a PR for {head} on {self.origin_repo} using {self.push_repo}"
        )
        auth = HTTPBasicAuth(self.github_user, self.github_token)
        apiurl = f"https://api.github.com/repos/{self.origin_repo}/pulls"
        r = requests.post(
            apiurl,
            auth=auth,
            json={
                "head": head,
                "base": "master",
                "title": "Contribution from test-lists.ooni.org",
            },
        )
        j = r.json()
        try:
            url = j["url"]
            return url
        except KeyError:
            log.error(f"Failed to retrieve URL for the PR {j}")
            raise

    def _check_pr_id(self, pr_id: str):
        if not pr_id.startswith("https"):
            raise InvalidPullRequestState(
                description=f"pr_id {pr_id!r} doesn't look like a URL"
            )

    def _close_pr(self, account_id):
        pr_id = self._get_pr_id(account_id)
        self._check_pr_id(pr_id)
        log.info(f"closing PR {pr_id}")
        auth = HTTPBasicAuth(self.github_user, self.github_token)
        r = requests.patch(pr_id, json={"state": "closed"}, auth=auth)
        if r.status_code != 200:
            # NOTE: this used to be a bare `assert r.status_code == 200`,
            # which is both invisible under `python -O` and previously had
            # zero test coverage. This can genuinely happen - e.g. a race
            # between the PR being closed here and it being merged
            # upstream - so raise a real, catchable error instead.
            log.error(
                f"[git-debug] account={account_id} failed to close PR "
                f"{pr_id}: GitHub returned status {r.status_code}"
            )
            raise CannotClosePR()

    def _is_pr_resolved(self, account_id) -> bool:
        """Raises if the PR was never opened"""
        pr_id = self._get_pr_id(account_id)
        self._check_pr_id(pr_id)
        log.debug(f"Fetching PR {pr_id}")
        auth = HTTPBasicAuth(self.github_user, self.github_token)
        r = requests.get(pr_id, auth=auth)
        j = r.json()
        if "state" not in j:
            raise InvalidPullRequestState(
                description=f"GitHub's PR status response is missing 'state': {j!r}"
            )
        return j["state"] != "open"

    def _push_to_repo(self, account_id):
        with git.Repo(self.repo_dir) as repo:
            branch_name = self._get_user_branchname(account_id)
            local_head = _read_ref(repo, f"refs/heads/{branch_name}")

            # NOTE: comparing refs/heads/<branch> in the shared repo against
            # HEAD in the user's worktree is *not* a useful check on its
            # own: HEAD in a worktree is a symref pointing at the exact
            # same ref storage in the shared commondir, so the two always
            # agree by construction - they're two views of one ref file,
            # not two independent copies. The actual failure mode we're
            # guarding against (git.add()/git.commit() raising after the
            # CSV rename, per the original bug report) leaves the change
            # sitting uncommitted in the worktree's index/working tree,
            # which a ref comparison can never see. Check the worktree's
            # status instead.
            user_repo_path = self._get_user_repo_path(account_id)
            if os.path.exists(user_repo_path):
                with git.Repo(user_repo_path) as user_repo:
                    worktree_head = _read_ref(user_repo, "HEAD")
                    dirty = git.status(user_repo)
                    log.debug(
                        f"[git-debug] account={account_id} pushing {branch_name} "
                        f"to GitHub, local_head={local_head} "
                        f"worktree_head={worktree_head} status={dirty}"
                    )
                    has_uncommitted = bool(
                        any(dirty.staged.values()) or dirty.unstaged
                    )
                    if has_uncommitted:
                        # This is exactly the failure mode from the original
                        # bug report: a CSV edit landed on disk in the
                        # user's worktree (git.add() and/or git.commit()
                        # raised right after the rename) but was never
                        # committed, so it never reached refs/heads/<branch>
                        # in the shared repo. Pushing now would silently
                        # open/update a PR that's missing this change.
                        log.error(
                            f"[git-debug] account={account_id} branch "
                            f"{branch_name} worktree has uncommitted changes "
                            f"(staged={dirty.staged} unstaged={dirty.unstaged}) "
                            "- refusing to push, this change was never "
                            "actually committed"
                        )
                        raise CannotUpdateList(
                            description="The user's worktree has uncommitted "
                            "changes that never made it into a commit"
                        )
            else:
                log.debug(
                    f"[git-debug] account={account_id} pushing {branch_name} "
                    f"to GitHub, local_head={local_head} (no worktree checked "
                    "out - nothing to verify)"
                )

            refspec = f"refs/heads/{branch_name}:refs/heads/{branch_name}"
            git.push(repo, "rworigin", refspecs=[refspec], force=True)
            log.debug(
                f"[git-debug] account={account_id} pushed {branch_name} "
                f"(sha={local_head}) to rworigin"
            )

    @timer(name="citizenlab_propose_changes")
    def propose_changes(self, account_id: str) -> str:
        """Push the account's branch and open a PR for it. Returns the PR's
        API URL.

        NOTE: this used to swallow any failure from _push_to_repo()/
        _open_pr() and return "" with an implicit HTTP 200 - the frontend
        would then render a fake "Submitted!" success with a dead PR link
        while the backend state silently stayed IN_PROGRESS. Both failure
        modes now raise CannotProposeChanges() so the caller actually sees
        the failure; retrying is expected to work once the underlying
        issue clears, and no change is lost even if the push succeeded but
        opening the PR failed, since submit() can simply be called again.
        """
        log.debug("proposing changes")
        try:
            self._push_to_repo(account_id)
        except Exception:
            log.exception(f"[git-debug] account={account_id} failed to push to repo")
            raise CannotProposeChanges()

        branch_name = self._get_user_branchname(account_id)
        try:
            pr_id = self._open_pr(branch_name)
        except Exception:
            log.exception(
                f"[git-debug] account={account_id} branch {branch_name} "
                "was pushed successfully but opening the PR failed - "
                "the change is not lost, retrying submit() will pick up "
                "the already-pushed branch and try to open the PR again"
            )
            raise CannotProposeChanges()

        self._set_pr_id(account_id, pr_id)
        self._set_state(account_id, "PR_OPEN")
        return pr_id
