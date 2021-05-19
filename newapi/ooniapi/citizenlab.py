"""
Citizenlab CRUD API
"""

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from hashlib import sha224
from typing import List
import csv
import io
import os
import re
import shutil

from requests.auth import HTTPBasicAuth
from filelock import FileLock  # debdeps: python3-filelock
from flask import Blueprint, current_app, request, make_response, jsonify
from werkzeug.exceptions import HTTPException
import git  # debdeps: python3-git
import requests

from ooniapi.auth import role_required

"""

URL prioritization:
create_url_priorities_table() creates the url_priorities table.
It contains rules on category_code, cc, domain and url to assign priorities.
Values can be wildcards "*". A citizenlab entry can match multiple rules.
"""

# TODO: add per-user locking

log = None

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


def jerror(msg, code=400):
    return make_response(jsonify(error=msg), code)


class DuplicateURL(Exception):
    pass


class ProgressPrinter(git.RemoteProgress):
    def update(self, op_code, cur_count, max_count=None, message=""):
        print(
            op_code,
            cur_count,
            max_count,
            cur_count / (max_count or 100.0),
            message or "NO MESSAGE",
        )


def safe(username: str) -> str:
    """Convert username to a filesystem-safe string"""
    return sha224("aoeu".encode()).hexdigest()


class URLListManager:
    def __init__(self, working_dir, github_token, push_repo, origin_repo):
        self.working_dir = working_dir
        self.push_repo = push_repo
        self.github_user = push_repo.split("/")[0]
        self.github_token = github_token

        self.origin_repo = origin_repo
        self.repo_dir = self.working_dir / "test-lists"

        self.repo = self.init_repo()

    def init_repo(self):
        log.debug("initializing repo")
        if not os.path.exists(self.repo_dir):
            log.debug("cloning repo")
            url = f"https://github.com/{self.origin_repo}.git"
            repo = git.Repo.clone_from(url, self.repo_dir, branch="master")
            url = f"https://{self.github_user}:{self.github_token}@github.com/{self.push_repo}.git"
            repo.create_remote("rworigin", url)
        repo = git.Repo(self.repo_dir)
        repo.remotes.origin.pull(progress=ProgressPrinter())
        return repo

    def get_user_repo_path(self, username) -> Path:
        return self.working_dir / "users" / safe(username) / "test-lists"

    def get_user_statefile_path(self, username) -> Path:
        return self.working_dir / "users" / safe(username) / "state"

    def get_user_pr_path(self, username) -> Path:
        return self.working_dir / "users" / safe(username) / "pr_id"

    def get_user_branchname(self, username: str) -> str:
        # FIXME: username is not trusted
        return f"user-contribution/{username}"

    def get_state(self, username: str):
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
            return self.get_user_statefile_path(username).read_text()
        except FileNotFoundError:
            return "CLEAN"

    def set_state(self, username, state: str):
        """
        This will record the current state of the pull request for the user to
        the statefile.
        The absence of a statefile is an indication of a clean state.
        """
        assert state in ("IN_PROGRESS", "PR_OPEN", "CLEAN")
        log.debug(f"setting state for {username} to {state}")
        if state == "CLEAN":
            self.get_user_statefile_path(username).unlink()
            self.get_user_pr_path(username).unlink()
            return

        with open(self.get_user_statefile_path(username), "w") as out_file:
            out_file.write(state)

    def set_pr_id(self, username: str, pr_id):
        self.get_user_pr_path(username).write_text(pr_id)

    def get_pr_id(self, username: str):
        return self.get_user_pr_path(username).read_text()

    def get_user_repo(self, username: str):
        repo_path = self.get_user_repo_path(username)
        if not os.path.exists(repo_path):
            log.info(f"creating {repo_path}")
            self.repo.git.worktree(
                "add", "-b", self.get_user_branchname(username), repo_path
            )
        return git.Repo(repo_path)

    def get_user_lock(self, username: str):
        lockfile_f = self.working_dir / "users" / safe(username) / "state.lock"
        return FileLock(lockfile_f, timeout=5)

    def get_test_list(self, username, country_code):
        country_code = country_code.lower()
        if len(country_code) != 2 and country_code != "global":
            raise Exception("Invalid country code")

        self.sync_state(username)
        self.pull_origin_repo()

        repo_path = self.get_user_repo_path(username)
        if not os.path.exists(repo_path):
            repo_path = self.repo_dir

        test_list = []
        path = repo_path / "lists" / f"{country_code}.csv"
        log.debug(f"Reading {path}")
        with path.open() as tl_file:
            csv_reader = csv.reader(tl_file)
            for line in csv_reader:
                test_list.append(line)
        return test_list

    def is_duplicate_url(self, username, country_code, new_url):
        url_set = set()
        for row in self.get_test_list(username, country_code):
            url = row[0]
            url_set.add(url)
        if country_code != "global":
            for row in self.get_test_list(username, "global"):
                url = row[0]
                url_set.add(url)
        return new_url in url_set

    def pull_origin_repo(self):
        self.repo.remotes.origin.pull(progress=ProgressPrinter())

    def sync_state(self, username):
        state = self.get_state(username)

        # If the state is CLEAN or IN_PROGRESS we don't have to do anything
        if state == "CLEAN":
            return
        if state == "IN_PROGRESS":
            return
        if self.is_pr_resolved(username):
            shutil.rmtree(self.get_user_repo_path(username))
            self.repo.git.worktree("prune")
            self.repo.delete_head(self.get_user_branchname(username), force=True)

            self.set_state(username, "CLEAN")

    def add(self, username, cc, new_entry, comment):
        self.sync_state(username)
        self.pull_origin_repo()
        log.debug("adding new entry")
        state = self.get_state(username)
        if state in ("PR_OPEN"):
            raise Exception("You cannot edit files while changes are pending")

        repo = self.get_user_repo(username)
        with self.get_user_lock(username):
            csv_f = self.get_user_repo_path(username) / "lists" / f"{cc}.csv"

            if self.is_duplicate_url(username, cc, new_entry[0]):
                raise DuplicateURL()

            log.debug(f"Writing {csv_f}")
            with csv_f.open("a") as out_file:
                csv_writer = csv.writer(
                    out_file, quoting=csv.QUOTE_MINIMAL, lineterminator="\n"
                )
                csv_writer.writerow(new_entry)

            log.debug(f"Writtten {csv_f}")
            repo.index.add([csv_f.as_posix()])
            repo.index.commit(comment)

            self.set_state(username, "IN_PROGRESS")

    def update(self, username, cc, old_entry, new_entry, comment):
        log.debug("updating existing entry")
        cc = cc.lower()
        if len(cc) != 2:
            raise Exception("Invalid country code")

        self.sync_state(username)
        self.pull_origin_repo()
        state = self.get_state(username)
        if state in ("PR_OPEN"):
            raise Exception("Your changes are being reviewed. Please wait.")

        if old_entry == new_entry:
            raise Exception("No change is being made.")

        repo = self.get_user_repo(username)
        with self.get_user_lock(username):

            csv_f = self.get_user_repo_path(username) / "lists" / f"{cc}.csv"

            new_url = new_entry[0]
            if new_url != old_entry[0]:
                # If the URL is being changed check for collisions
                if self.is_duplicate_url(username, cc, new_url):
                    raise DuplicateURL()

            out_buffer = io.StringIO()
            with csv_f.open() as in_file:
                csv_reader = csv.reader(in_file)
                csv_writer = csv.writer(
                    out_buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\n"
                )

                found = False
                for row in csv_reader:
                    if row == old_entry:
                        found = True
                        csv_writer.writerow(new_entry)
                    else:
                        csv_writer.writerow(row)

            if not found:
                m = "Unable to update. The URL list has changed in the meantime."
                raise Exception(m)

            with csv_f.open("w") as out_file:
                out_buffer.seek(0)
                shutil.copyfileobj(out_buffer, out_file)
            repo.index.add([csv_f.as_posix()])
            repo.index.commit(comment)

            self.set_state(username, "IN_PROGRESS")

    def open_pr(self, branchname):
        head = f"{self.github_user}:{branchname}"
        log.debug(f"opening a PR for {head}")
        auth = HTTPBasicAuth(self.github_user, self.github_token)
        r = requests.post(
            f"https://api.github.com/repos/{self.origin_repo}/pulls",
            auth=auth,
            json={
                "head": head,
                "base": "master",
                "title": "Pull requests from the web",
            },
        )
        j = r.json()
        # log.debug(j)
        return j["url"]

    def is_pr_resolved(self, username):
        pr_id = (self.get_pr_id(username),)
        auth = HTTPBasicAuth(self.github_user, self.github_token)
        r = requests.post(pr_id, auth=auth)
        j = r.json()
        return j["state"] != "open"

    def push_to_repo(self, username):
        log.debug("pushing branch to GitHub")
        self.repo.remotes.rworigin.push(
            self.get_user_branchname(username),
            progress=ProgressPrinter(),
            force=True,
        )

    def propose_changes(self, username: str) -> str:
        with self.get_user_lock(username):
            log.debug("proposing changes")
            self.set_state(username, "PR_OPEN")
            self.push_to_repo(username)
            pr_id = self.open_pr(self.get_user_branchname(username))
            self.set_pr_id(username, pr_id)
            return pr_id


class BadURL(HTTPException):
    code = 400
    description = "Invalid URL"


class BadCategoryCode(HTTPException):
    code = 400
    description = "Invalid category code"


class BadCategoryDescription(HTTPException):
    code = 400
    description = "Invalid category description"


class BadDate(HTTPException):
    code = 400
    description = "Invalid date"


def check_url(url):
    if not VALID_URL.match(url):
        raise BadURL()
    elif any([c in url for c in BAD_CHARS]):
        raise BadURL()
    elif url != url.strip():
        raise BadURL()
    elif urlparse(url).path == "":
        raise BadURL()


def validate_entry(entry: List[str]) -> None:
    url, category_code, category_desc, date_str, user, notes = entry
    check_url(url)
    if category_code not in CATEGORY_CODES:
        raise BadCategoryCode()
    if category_desc != CATEGORY_CODES[category_code]:
        raise BadCategoryDescription()
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
        if d != date_str:
            raise BadDate()
    except Exception:
        raise BadDate()


def get_username():
    return request._user_nickname


def get_url_list_manager():
    conf = current_app.config
    return URLListManager(
        working_dir=Path(conf["GITHUB_WORKDIR"]),
        github_token=conf["GITHUB_TOKEN"],
        origin_repo=conf["GITHUB_ORIGIN_REPO"],
        push_repo=conf["GITHUB_PUSH_REPO"],
    )


@cz_blueprint.route("/api/v1/url-submission/test-list/<country_code>", methods=["GET"])
@role_required(["admin", "user"])
def get_test_list(country_code):
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
    username = get_username()
    ulm = get_url_list_manager()
    tl = ulm.get_test_list(username, country_code)
    return make_response(jsonify(tl))


@cz_blueprint.route("/api/v1/url-submission/add-url", methods=["POST"])
@role_required(["admin", "user"])
def url_submission_add_url():
    """Submit a new citizenlab URL entry
    ---
    parameters:
      - in: body
        name: add new URL
        required: true
        schema:
          type: object
          properties:
            country_code:
              type: string
            comment:
              type: string
            new_entry:
              type: array
    responses:
      200:
        description: New URL confirmation
        schema:
          type: object
          properties:
            new_entry:
              type: array
    """
    global log
    log = current_app.logger
    try:
        username = get_username()
        ulm = get_url_list_manager()
        validate_entry(request.json["new_entry"])
        ulm.add(
            username=username,
            cc=request.json["country_code"],
            new_entry=request.json["new_entry"],
            comment=request.json["comment"],
        )
        d = {"new_entry": request.json["new_entry"]}
        return make_response(jsonify(d))
    except Exception as e:
        log.info(f"URL submission add error {e}", exc_info=1)
        return jerror(str(e))


@cz_blueprint.route("/api/v1/url-submission/update-url", methods=["POST"])
@role_required(["admin", "user"])
def url_submission_update_url():
    """Update a citizenlab URL entry.
    The current value needs to be sent back as "old_entry" as a check
    against race conditions
    ---
    parameters:
      - in: body
        name: add new URL
        required: true
        schema:
          type: object
          properties:
            country_code:
              type: string
            comment:
              type: string
            new_entry:
              type: array
            old_entry:
              type: array
    responses:
      200:
        description: New URL confirmation
        schema:
          type: object
          properties:
            updated_entry:
              type: array
    """
    global log
    log = current_app.logger
    username = get_username()

    ulm = get_url_list_manager()
    validate_entry(request.json["new_entry"])
    try:
        ulm.update(
            username=username,
            cc=request.json["country_code"],
            old_entry=request.json["old_entry"],
            new_entry=request.json["new_entry"],
            comment=request.json["comment"],
        )
        return jsonify({"updated_entry": request.json["new_entry"]})
    except Exception as e:
        log.info(f"URL submission update error {e}", exc_info=1)
        return jerror(str(e))


@cz_blueprint.route("/api/v1/url-submission/state", methods=["GET"])
@role_required(["admin", "user"])
def get_workflow_state():
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
    username = get_username()
    log.debug("get citizenlab workflow state")
    ulm = get_url_list_manager()
    state = ulm.get_state(username)
    return jsonify(state=state)


@cz_blueprint.route("/api/v1/url-submission/submit", methods=["POST"])
@role_required(["admin", "user"])
def post_propose_changes():
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
    username = get_username()
    ulm = get_url_list_manager()
    pr_id = ulm.propose_changes(username)
    return jsonify(pr_id=pr_id)


# # Prioritization management # #


def create_url_priorities_table() -> None:
    # See description in module docstring
    log = current_app.logger
    sql = "SELECT to_regclass('url_priorities')"
    q = current_app.db_session.execute(sql)
    if q.fetchone()[0] is not None:
        return  # table already present

    log.info("Creating table url_priorities")
    sql = """
CREATE TABLE public.url_priorities (
    category_code text,
    cc text,
    domain text,
    url text,
    priority smallint NOT NULL,
    UNIQUE (category_code, cc, domain, url)
);
COMMENT ON COLUMN public.url_priorities.domain IS 'FQDN or ipaddr without http and port number';
COMMENT ON COLUMN public.url_priorities.category_code IS 'Category from Citizen Lab';
GRANT SELECT ON TABLE public.url_priorities TO readonly;
GRANT SELECT ON TABLE public.url_priorities TO shovel;
GRANT SELECT ON TABLE public.url_priorities TO amsapi;
"""
    current_app.db_session.execute(sql)

    log.info("Populating table url_priorities")
    sql = """INSERT INTO url_priorities
        (category_code, cc, domain, url, priority)
        VALUES(:category_code, '*', '*', '*', :priority)"""
    category_priorities = {
        "NEWS": 100,
        "POLR": 100,
        "HUMR": 100,
        "LGBT": 100,
        "ANON": 100,
        "GRP": 80,
        "COMT": 80,
        "MMED": 80,
        "SRCH": 80,
        "PUBH": 80,
        "REL": 60,
        "XED": 60,
        "HOST": 60,
        "ENV": 60,
        "FILE": 40,
        "CULTR": 40,
        "IGO": 40,
        "GOVT": 40,
        "DATE": 30,
        "HATE": 30,
        "MILX": 30,
        "PROV": 30,
        "PORN": 30,
        "GMB": 30,
        "ALDR": 30,
        "GAME": 20,
        "MISC": 20,
        "HACK": 20,
        "ECON": 20,
        "COMM": 20,
        "CTRL": 20,
    }
    for cat, prio in category_priorities.items():
        d = dict(category_code=cat, priority=prio)
        current_app.db_session.execute(sql, d)
    current_app.db_session.commit()


@cz_blueprint.route("/api/_/url-priorities/list", methods=["GET"])
@role_required(["admin"])
def list_url_priorities():
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
    FROM url_priorities"""
    q = current_app.db_session.execute(query)
    row = [dict(r) for r in q]
    return make_response(jsonify(rules=row))


@cz_blueprint.route("/api/_/url-priorities/update", methods=["POST"])
@role_required(["admin"])
def post_update_url_priority():
    """Add/update/delete an URL priority rule
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
        return jerror("Pointless update", 400)

    # Use an explicit marker "*" to represent "match everything" because NULL
    # cannot be used in UNIQUE constraints; also "IS NULL" is difficult to
    # handle in query generation. See match_prio_rule(...)
    for k in ["category_code", "cc", "domain", "url", "priority"]:
        if old and k not in old:
            old[k] = "*"
        if new and k not in new:
            new[k] = "*"

    assert old or new
    if old:  # delete an existing rule
        query = """DELETE FROM url_priorities
        WHERE category_code = :category_code
        AND cc = :cc
        AND domain = :domain
        AND url = :url
        AND priority = :priority
        """
        q = current_app.db_session.execute(query, old).rowcount
        if q < 1:
            return jerror("Old rule not found", 400)

    if new:  # add new rule
        query = """INSERT INTO url_priorities
            (category_code, cc, domain, url, priority)
            VALUES(:category_code, :cc, :domain, :url, :priority)
        """
        try:
            q = current_app.db_session.execute(query, new).rowcount
        except Exception as e:
            log.info(str(e))
            current_app.db_session.rollback()
            return jerror("Duplicate rule", 400)

    current_app.db_session.commit()
    return make_response(jsonify(q))


def match_prio_rule(cz, pr: dict) -> bool:
    """Match a priority rule to citizenlab entry
    """
    for k in ["category_code", "cc", "domain", "url"]:
        if pr[k] not in ("*", cz[k]):
            return False

    return True


def compute_url_priorities():
    log = current_app.logger
    sql = "SELECT category_code, cc, domain, url, priority FROM citizenlab"
    q = current_app.db_session.execute(sql)
    citizenlab = [dict(r) for r in q]
    sql = "SELECT category_code, cc, domain, url, priority FROM url_priorities"
    q = current_app.db_session.execute(sql)
    prio_rules = [dict(r) for r in q]
    assert prio_rules
    match_attempt_cnt = 0
    match_cnt = 0
    for cz in citizenlab:
        cz["priority"] = 0
        for pr in prio_rules:
            match_attempt_cnt += 1
            if match_prio_rule(cz, pr):
                match_cnt += 1
                cz["priority"] += pr["priority"]

    perc = match_cnt / match_attempt_cnt * 100
    log.info(f"Prioritization rules match percentage {perc}")
    return citizenlab


# TODO: remove this
@cz_blueprint.route("/api/_/url-priorities/WIP", methods=["GET"])
def get_computed_url_priorities():
    log = current_app.logger
    try:
        create_url_priorities_table()
        p = compute_url_priorities()
        return jsonify(p)
    except Exception as e:
        log.error(e, exc_info=1)
        return jerror(str(e), 400)
