"""
Citizenlab CRUD API
"""

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, List, Optional
import csv
import logging
import os
import re
import shutil
import json

from requests.auth import HTTPBasicAuth
from filelock import FileLock  # debdeps: python3-filelock
from flask import Blueprint, current_app, request, make_response, jsonify, Response
from werkzeug.exceptions import HTTPException
import git  # debdeps: python3-git
import requests
from sqlalchemy import sql

from ooniapi.auth import role_required
from ooniapi.database import query_click, query_click_one_row, insert_click
from ooniapi.utils import nocachejson, cachedjson

"""

URL prioritization: uses the url_priorities table.
It contains rules on category_code, cc, domain and url to assign priorities.
Values can be wildcards "*". A citizenlab entry can match multiple rules.
"""

log = logging.getLogger()  # overridden by current_app.logger

cz_blueprint = Blueprint("citizenlab_api", "citizenlab")


VALID_URL = regex = re.compile(
    r"^(?:http)s?://"  # http:// or https://
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain...
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
    r"(?::\d+)?"  # optional port
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)

BAD_CHARS = ["\r", "\n", "\t", "\\"]

# TODO: move out
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

class BaseOONIException(HTTPException):
    code: int = 400
    err_str: str = "err_generic_ooni_exception"
    err_args: Optional[Dict[str, str]] = None
    description: str = "Generic OONI error"

    def __init__(
        self,
        description: Optional[str] = None,
        err_args: Optional[Dict[str, str]] = None,
    ):
        super().__init__(description=description)
        if err_args is not None:
            self.err_args = err_args


class BadURL(BaseOONIException):
    code = 400
    err_str = "err_bad_url"
    description = "Invalid URL"


class BadCategoryCode(BaseOONIException):
    code = 400
    err_str = "err_bad_category_code"
    description = "Invalid category code"

class BadCategoryDescription(BaseOONIException):
    code = 400
    err_str = "err_bad_category_description"
    description = "Invalid category description"

class BadDate(BaseOONIException):
    code = 400
    err_str = "err_bad_date"
    description = "Invalid date"

class CountryNotSupported(BaseOONIException):
    code = 400
    err_str = "err_country_not_supported"
    description = "Country Not Supported"

class InvalidCountryCode(BaseOONIException):
    code = 400
    err_str = "err_invalid_country_code"
    description = "Country code is invalid"

class DuplicateURLError(BaseOONIException):
    code = 400
    err_str = "err_duplicate_url"
    description = "Duplicate URL"

class DuplicateRuleError(BaseOONIException):
    code = 400
    err_str = "err_duplicate_rule"
    description = "Duplicate rule"

class RuleNotFound(BaseOONIException):
    code = 404
    err_str = "err_rule_not_found"
    description = "Rule not found error"

class CannotClosePR(BaseOONIException):
    code = 400
    err_str = "err_cannot_close_pr"
    description = "Unable to close PR. Please reload data."

class CannotUpdateList(BaseOONIException):
    code = 400
    err_str = "err_cannot_update_list"
    description = "Unable to update. The URL list has changed in the meantime."

class NoProposedChanges(BaseOONIException):
    code = 400
    err_str = "err_no_proposed_changes"
    description = "No changes are being proposed"

def jerror(err, code=400):
    if isinstance(err, BaseOONIException):
        err_j = {
            "error": err.description,
            "err_str": err.err_str,
        }
        if err.err_args:
            err_j["err_args"] = err.err_args
        return make_response(jsonify(err_j), err.code)

    return make_response(jsonify(error=str(err)), code)


class ProgressPrinter(git.RemoteProgress):
    def update(self, op_code, cur_count, max_count=None, message=""):
        print(
            op_code,
            cur_count,
            max_count,
            cur_count / (max_count or 100.0),
            message or "NO MESSAGE",
        )


class URLListManager:
    def __init__(self, working_dir, github_user, github_token, push_repo, origin_repo):
        self.working_dir = working_dir
        self.origin_repo = origin_repo
        self.push_repo = push_repo
        self.github_user = github_user
        self.github_token = github_token
        self.repo_dir = self.working_dir / "test-lists"
        self.push_username = push_repo.split("/")[0]

        self.repo = self.init_repo()

    def init_repo(self):
        if not os.path.exists(self.repo_dir):
            log.info(f"cloning {self.origin_repo} repository")
            url = f"https://github.com/{self.origin_repo}.git"
            repo = git.Repo.clone_from(url, self.repo_dir, branch="master")
            url = f"https://{self.github_user}:{self.github_token}@github.com/{self.push_repo}.git"
            repo.create_remote("rworigin", url)
        repo = git.Repo(self.repo_dir)
        repo.remotes.origin.pull(progress=ProgressPrinter())
        return repo

    def get_user_repo_path(self, account_id) -> Path:
        return self.working_dir / "users" / account_id / "test-lists"

    def get_user_statefile_path(self, account_id) -> Path:
        return self.working_dir / "users" / account_id / "state"

    def get_user_pr_path(self, account_id) -> Path:
        return self.working_dir / "users" / account_id / "pr_id"

    def get_user_changes_path(self, account_id) -> Path:
        return self.working_dir / "users" / account_id / "changes.pickle"

    def get_user_branchname(self, account_id: str) -> str:
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
            return self.get_user_statefile_path(account_id).read_text()
        except FileNotFoundError:
            return "CLEAN"

    def set_state(self, account_id, state: str):
        """
        This will record the current state of the pull request for the user to
        the statefile.
        The absence of a statefile is an indication of a clean state.
        """
        assert state in ("IN_PROGRESS", "PR_OPEN", "CLEAN"), "Unexpected state"
        log.debug(f"setting state for {account_id} to {state}")
        if state == "CLEAN":
            self.get_user_statefile_path(account_id).unlink()
            self.get_user_pr_path(account_id).unlink()
            return

        with open(self.get_user_statefile_path(account_id), "w") as out_file:
            out_file.write(state)

    def set_pr_id(self, account_id: str, pr_id):
        self.get_user_pr_path(account_id).write_text(pr_id)

    def get_pr_id(self, account_id: str):
        """Returns an API URL e.g.
        https://api.github.com/repos/citizenlab/test-lists/pulls/800
        Raises if the PR was never opened
        """
        return self.get_user_pr_path(account_id).read_text()

    def get_pr_url(self, account_id: str):
        """Returns a browsable URL
        Raises if the PR was never opened
        """
        apiurl = self.get_pr_id(account_id)
        pr_num = apiurl.split("/")[-1]
        return f"https://github.com/{self.origin_repo}/pull/{pr_num}"

    def get_user_repo(self, account_id: str):
        repo_path = self.get_user_repo_path(account_id)
        if not os.path.exists(repo_path):
            log.info(f"creating {repo_path}")
            self.repo.git.worktree(
                "add", "-b", self.get_user_branchname(account_id), repo_path
            )
        return git.Repo(repo_path)

    def get_user_lock(self, account_id: str):
        lockfile_f = self.working_dir / "users" / account_id / "state.lock"
        return FileLock(lockfile_f, timeout=5)

    def get_test_list(self, account_id, country_code) -> List[Dict[str, str]]:
        country_code = country_code.lower()
        if len(country_code) != 2 and country_code != "global":
            raise InvalidCountryCode()

        self.sync_state(account_id)
        self.pull_origin_repo()

        repo_path = self.get_user_repo_path(account_id)
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

    def prevent_duplicate_url(self, account_id, country_code, new_url):
        rows = self.get_test_list(account_id, country_code)
        if country_code != "global":
            rows.extend(self.get_test_list(account_id, "global"))

        if new_url in (r["url"] for r in rows):
            raise DuplicateURLError(
                    description=f"{new_url} is duplicate",
                    err_args={"url": new_url}
            )

    def pull_origin_repo(self):
        self.repo.remotes.origin.pull(progress=ProgressPrinter())

    def sync_state(self, account_id):
        state = self.get_state(account_id)

        # If the state is CLEAN or IN_PROGRESS we don't have to do anything
        if state == "CLEAN":
            return
        if state == "IN_PROGRESS":
            return
        if self.is_pr_resolved(account_id):
            path = self.get_user_repo_path(account_id)
            bname = self.get_user_branchname(account_id)
            log.debug(f"Deleting {path}")
            try:
                # TODO: investigate
                shutil.rmtree(path)
                self.repo.git.worktree("prune")
                self.repo.delete_head(bname, force=True)
                self.maybe_delete_changes_log(account_id)
            except Exception as e:
                log.info(f"Error deleting {path} {e}")

            self.set_state(account_id, "CLEAN")

    def maybe_delete_changes_log(self, account_id):
        changes_log = self.get_user_changes_path(account_id)
        try:
            changes_log.unlink()
        except FileNotFoundError:
            pass

    def read_changes_log(self, account_id):
        changes_log = self.get_user_changes_path(account_id)
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

        with self.get_user_changes_path(account_id).open("w") as out_file:
            json.dump(changeset, out_file)

    def update(
        self, account_id: str, cc: str, old_entry: dict, new_entry: dict, comment: str
    ):
        """
        Create/update/delete test list entries.
        """
        # TODO: set date_added to now() on new_entry
        # fields follow the order in the CSV files
        if old_entry:
            old_entry["category_description"] = CATEGORY_CODES[
                old_entry["category_code"]
            ]
            assert sorted(old_entry.keys()) == sorted(
                CITIZENLAB_CSV_HEADER
            ), "Unexpected keys"

        if new_entry:
            new_entry["category_description"] = CATEGORY_CODES[
                new_entry["category_code"]
            ]
            assert sorted(new_entry.keys()) == sorted(
                CITIZENLAB_CSV_HEADER
            ), "Unexpected keys"

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

        self.pull_origin_repo()
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
            try:
                self.close_pr(account_id)
            except AssertionError:
                # This might happen due to a race between the PR being closed
                # and it being merged upstream
                raise CannotClosePR()
            self.set_state(account_id, "IN_PROGRESS")

        repo = self.get_user_repo(account_id)
        with self.get_user_lock(account_id):
            csv_f = self.get_user_repo_path(account_id) / "lists" / f"{cc}.csv"
            tmp_f = csv_f.with_suffix(".tmp")

            if new_entry:
                # Check for collisions:
                if not old_entry:
                    self.prevent_duplicate_url(account_id, cc, new_entry["url"])

                elif old_entry and new_entry["url"] != old_entry["url"]:
                    # If the URL is being changed check for collisions
                    self.prevent_duplicate_url(account_id, cc, new_entry["url"])

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
            repo.index.add([csv_f.as_posix()])
            repo.index.commit(comment)

            self.write_changes_log(account_id, cc, old_entry, new_entry)

            self.set_state(account_id, "IN_PROGRESS")

    def open_pr(self, branchname):
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

    def close_pr(self, account_id):
        pr_id = self.get_pr_id(account_id)
        assert pr_id.startswith("https"), f"{pr_id} doesn't start with https"
        log.info(f"closing PR {pr_id}")
        auth = HTTPBasicAuth(self.github_user, self.github_token)
        r = requests.patch(pr_id, json={"state": "closed"}, auth=auth)
        assert r.status_code == 200

    def is_pr_resolved(self, account_id) -> bool:
        """Raises if the PR was never opened"""
        pr_id = self.get_pr_id(account_id)
        assert pr_id.startswith("https"), f"{pr_id} doesn't start with https"
        log.debug(f"Fetching PR {pr_id}")
        auth = HTTPBasicAuth(self.github_user, self.github_token)
        r = requests.get(pr_id, auth=auth)
        j = r.json()
        assert "state" in j
        return j["state"] != "open"

    def push_to_repo(self, account_id):
        log.debug("pushing branch to GitHub")
        self.repo.remotes.rworigin.push(
            self.get_user_branchname(account_id),
            progress=ProgressPrinter(),
            force=True,
        )

    def propose_changes(self, account_id: str) -> str:
        with self.get_user_lock(account_id):
            log.debug("proposing changes")
            self.push_to_repo(account_id)
            pr_id = self.open_pr(self.get_user_branchname(account_id))
            self.set_pr_id(account_id, pr_id)
            self.set_state(account_id, "PR_OPEN")
            return pr_id


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


def get_account_id():
    return request._account_id


def get_url_list_manager():
    conf = current_app.config
    return URLListManager(
        working_dir=Path(conf["GITHUB_WORKDIR"]),
        github_user=conf["GITHUB_USER"],
        github_token=conf["GITHUB_TOKEN"],
        origin_repo=conf["GITHUB_ORIGIN_REPO"],
        push_repo=conf["GITHUB_PUSH_REPO"],
    )


@cz_blueprint.route("/api/v1/url-submission/test-list/<country_code>", methods=["GET"])
@role_required(["admin", "user"])
def get_test_list(country_code) -> Response:
    """Fetch citizenlab URL list
    ---
    parameters:
      - in: path
        name: country_code
        type: string
        required: true
        description: 2-letter country code or "global"
    responses:
      200:
        description: URL list
        schema:
          type: object
          properties:
            new_entry:
              type: array
    """
    global log
    log = current_app.logger
    account_id = get_account_id()
    ulm = get_url_list_manager()
    try:
        tl = ulm.get_test_list(account_id, country_code)
        return nocachejson(tl)
    except BaseOONIException as e:
        return jerror(e)


@cz_blueprint.route("/api/v1/url-submission/update-url", methods=["POST"])
@role_required(["admin", "user"])
def url_submission_update_url() -> Response:
    """Create/update/delete a Citizenlab URL entry. The current value needs
    to be sent back as "old_entry" as a check against race conditions.
    Empty old_entry: create new rule. Empty new_entry: delete existing rule.
    ---
    parameters:
      - in: body
        required: true
        schema:
          type: object
          properties:
            country_code:
              type: string
            comment:
              type: string
            old_entry:
              type: object
              properties:
                category_code:
                  type: string
                url:
                  type: string
                date_added:
                  type: string
                user:
                  type: string
                notes:
                  type: string
            new_entry:
              type: object
              properties:
                category_code:
                  type: string
                url:
                  type: string
                date_added:
                  type: string
                user:
                  type: string
                notes:
                  type: string
    responses:
      200:
        description: New URL confirmation
        schema:
          type: object
          properties:
            updated_entry:
              type: object
    """
    global log
    log = current_app.logger
    account_id = get_account_id()

    ulm = get_url_list_manager()
    rj = request.json
    new = rj["new_entry"]
    old = rj["old_entry"]
    try:
        if new:
            validate_entry(new)
        if old:
            validate_entry(old)

        ulm.update(
            account_id=account_id,
            cc=rj["country_code"],
            old_entry=old,
            new_entry=new,
            comment=rj["comment"],
        )
        entry = request.json["new_entry"]
        return nocachejson(updated_entry=entry)
    except BaseOONIException as e:
        return jerror(e)


@cz_blueprint.route("/api/v1/url-submission/state", methods=["GET"])
@role_required(["admin", "user"])
def get_workflow_state() -> Response:
    """Get workflow state
    ---
    responses:
      200:
        description: New URL confirmation
        schema:
          type: object
    """
    global log
    log = current_app.logger
    account_id = get_account_id()
    log.debug("get citizenlab workflow state")
    ulm = get_url_list_manager()
    ulm.sync_state(account_id)
    state = ulm.get_state(account_id)
    if state in ("PR_OPEN"):
        pr_url = ulm.get_pr_url(account_id)
        return nocachejson(state=state, pr_url=pr_url)
    return nocachejson(state=state)


@cz_blueprint.route("/api/v1/url-submission/changes", methods=["GET"])
@role_required(["admin", "user"])
def get_changes() -> Response:
    """Get changes the user has made to the test list so far
    ---
    responses:
      200:
        description: A dictionary keyed on the country codes with the list of
            additions and deletions.
        schema:
          type: object
    """
    global log
    log = current_app.logger
    account_id = get_account_id()
    log.debug("get citizenlab git diff")
    ulm = get_url_list_manager()
    changes = ulm.read_changes_log(account_id)
    return nocachejson(changes=changes)


@cz_blueprint.route("/api/v1/url-submission/submit", methods=["POST"])
@role_required(["admin", "user"])
def post_propose_changes() -> Response:
    """Propose changes: open a Pull Request on GitHub
    ---
    responses:
      200:
        description: Pull request number
        type: object
    """
    global log
    log = current_app.logger
    log.info("submitting citizenlab changes")
    account_id = get_account_id()
    ulm = get_url_list_manager()
    try:
        pr_id = ulm.propose_changes(account_id)
        return nocachejson(pr_id=pr_id)
    except BaseOONIException as e:
        return jerror(e)


# # Prioritization management # #


@cz_blueprint.route("/api/_/url-priorities/list", methods=["GET"])
@role_required(["admin"])
def list_url_priorities() -> Response:
    """List URL priority rules
    ---
    responses:
      200:
        type: string
    """
    global log
    log = current_app.logger
    log.debug("listing URL prio rules")
    query = """SELECT category_code, cc, domain, url, priority
    FROM url_priorities FINAL
    ORDER BY category_code, cc, domain, url, priority
    """
    # The url_priorities table is CollapsingMergeTree
    q = query_click(sql.text(query), {})
    rows = list(q)
    try:
        return cachedjson("1s", rules=rows)
    except BaseOONIException as e:
        return jerror(e)


def initialize_url_priorities_if_needed():
    cntq = "SELECT count() AS cnt FROM url_priorities"
    cnt = query_click_one_row(sql.text(cntq), {})
    if cnt["cnt"] > 0:
        return

    rules = [
        ("NEWS", 100),
        ("POLR", 100),
        ("HUMR", 100),
        ("LGBT", 100),
        ("ANON", 100),
        ("MMED", 80),
        ("SRCH", 80),
        ("PUBH", 80),
        ("REL", 60),
        ("XED", 60),
        ("HOST", 60),
        ("ENV", 60),
        ("FILE", 40),
        ("CULTR", 40),
        ("IGO", 40),
        ("GOVT", 40),
        ("DATE", 30),
        ("HATE", 30),
        ("MILX", 30),
        ("PROV", 30),
        ("PORN", 30),
        ("GMB", 30),
        ("ALDR", 30),
        ("GAME", 20),
        ("MISC", 20),
        ("HACK", 20),
        ("ECON", 20),
        ("COMM", 20),
        ("CTRL", 20),
        ("COMT", 100),
        ("GRP", 100),
    ]
    rows = [
        {
            "sign": 1,
            "category_code": ccode,
            "cc": "*",
            "domain": "*",
            "url": "*",
            "priority": prio,
        }
        for ccode, prio in rules
    ]
    # The url_priorities table is CollapsingMergeTree
    query = """INSERT INTO url_priorities
        (sign, category_code, cc, domain, url, priority) VALUES
    """
    log.info("Populating url_priorities")
    r = insert_click(query, rows)
    return r


def validate_url_prio_rule_dict(r: dict):
    assert sorted(r.keys()) == ["category_code", "cc", "domain", "priority", "url"]


def update_url_priority_click(old: dict, new: dict):
    # The url_priorities table is CollapsingMergeTree
    # Both old and new might be set
    ins_sql = """INSERT INTO url_priorities
        (sign, category_code, cc, domain, url, priority) VALUES
    """
    if old:
        rule = old.copy()
        rule["sign"] = -1
        log.info(f"Deleting prioritization rule {rule}")
        r = insert_click(ins_sql, [rule])
        log.debug(f"Result: {r}")

    if new:
        q = """SELECT count() AS cnt FROM url_priorities FINAL WHERE sign = 1 AND
        category_code = :category_code AND cc = :cc AND domain = :domain
        AND url = :url"""
        cnt = query_click_one_row(sql.text(q), new)
        if cnt and cnt["cnt"] > 0:
            log.info(f"Rejecting duplicate rule {new}")
            raise DuplicateRuleError(err_args=new)

        rule = new.copy()
        rule["sign"] = 1
        log.info(f"Creating prioritization rule {rule}")
        r = insert_click(ins_sql, [rule])
        log.debug(f"Result: {r}")


@cz_blueprint.route("/api/_/url-priorities/update", methods=["POST"])
@role_required(["admin"])
def post_update_url_priority() -> Response:
    """Add/update/delete an URL priority rule. Empty old_entry: create new rule.
    Empty new_entry: delete existing rule. The current value needs to be sent
    back as "old_entry" as a check against race conditions
    ---
    parameters:
      - in: body
        name: add new URL
        required: true
        schema:
          type: object
          properties:
            old_entry:
              type: object
              properties:
                category_code:
                  type: string
                cc:
                  type: string
                domain:
                  type: string
                url:
                  type: string
                priority:
                  type: integer
            new_entry:
              type: object
              properties:
                category_code:
                  type: string
                cc:
                  type: string
                domain:
                  type: string
                url:
                  type: string
                priority:
                  type: integer
    responses:
      200:
        type: string
    """
    log = current_app.logger
    log.info("updating URL priority rule")
    old = request.json.get("old_entry", None)
    new = request.json.get("new_entry", None)
    if not old and not new:
        return jerror(NoProposedChanges())

    # Use an explicit marker "*" to represent "match everything" because NULL
    # cannot be used in UNIQUE constraints; also "IS NULL" is difficult to
    # handle in query generation. See match_prio_rule(...)
    for k in ["category_code", "cc", "domain", "url", "priority"]:
        if old and k not in old:
            old[k] = "*"
        if new and k not in new:
            new[k] = "*"

    assert old or new
    if old:
        validate_url_prio_rule_dict(old)

    if new:
        validate_url_prio_rule_dict(new)

    try:
        update_url_priority_click(old, new)
        return make_response(jsonify(1))
    except BaseOONIException as e:
        return jerror(e)
