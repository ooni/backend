import logging
import gc

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field
from sqlalchemy import sql

# Local imports
from testlists.common.auth import get_account_id_or_raise
from testlists.common.dependencies import role_required, SettingsDep, ClickhouseDep
from testlists.common.errors import *
from testlists.common.clickhouse_utils import query_click, query_click_one_row, insert_click
from testlists.common.routers import BaseModel
from testlists.common.utils import setnocacheresponse
from testlists.manager import get_url_list_manager


router = APIRouter()

log = logging.getLogger(__name__)


"""

URL prioritization: uses the url_priorities table.
It contains rules on category_code, cc, domain and url to assign priorities.
Values can be wildcards "*". A testlists entry can match multiple rules.
"""


class TestListResponse(BaseModel):
    test_list: Optional[List[Dict[str, Any]]] = Field(None, description="The fetched test list.")
    changes: Dict[str, Any] = Field(description="The changes related to the test list.")
    state: str = Field(description="The current sync state.")
    pr_url: Optional[str] = Field(None, description="The pull request URL, if applicable.")


@router.get(
    "/_/url-submission/test-list/{country_code}",
    response_model=TestListResponse,
    tags=["testlists"],
    dependencies=[Depends(role_required(["admin", "user"]))],
)
async def get_test_list_meta(
    request: Request,
    response: Response,
    settings: SettingsDep,
    country_code: str,
    ) -> TestListResponse:
    """Fetch testlists URL list and additional metadata.

    - **country_code**: 2-letter country code or "global".
    """

    try:
        account_id = get_account_id_or_raise(request.headers.get("Authorization"), settings.jwt_encryption_key)
    except Exception:
        raise HTTPException(detail="Authentication required", status_code=401)

    try:
        ulm = get_url_list_manager(settings, account_id)
        state = ulm.sync_state(account_id)
        pr_url = None

        if state == "PR_OPEN":
            pr_url = ulm.get_pr_url(account_id)

        changes = ulm.read_changes_log(account_id)

        try:
            tl = ulm.get_test_list(account_id, country_code)
        except CountryNotSupported:
            tl = None

        del ulm
        log.info("Forcing GC to unlock URLListManager immediately")
        gc.collect() # force gc to clean up and clear FileLock
        # Create the response object
        resp = TestListResponse(test_list=tl, changes=changes, state=state, pr_url=pr_url)
        setnocacheresponse(response)
        return resp
    except BaseOONIException as e:
        log.error(f"OONIException occurred: {e}")
        raise 
    except Exception as e:
        log.error(f"Unexpected error occurred: {e}")
        # Raise a generic HTTPException for unexpected errors
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


class UrlPriority(BaseModel):
    # XXX: it is unclear which fields are required to do an update
    # XXX: it looks like only domain and URL and cc and category_code are part of the
    # WHERE clause but the INTEG-TEST fields do not specifiy all of these fields
    # so the validator fails
    category_code: Optional[str] = Field("", description="The category code associated with the URL.")
    cc: Optional[str] = Field("", description="Country code that the URL is relevant to.")
    domain: Optional[str] = Field("", description="The domain of the URL.")
    url: Optional[str] = Field("", description="The actual URL to be prioritized.")
    priority: int = Field(..., description="The priority number for the URL. Higher numbers indicate higher priority.")


class ListUrlPriorityResponse(BaseModel):
    rules: List[UrlPriority] = Field(..., description="The list of UrlPriority items")


@router.get(
    "/_/url-priorities/list",
    tags=["testlists"],
    response_model=ListUrlPriorityResponse,
)
def list_url_priorities(
    clickhouse: ClickhouseDep,
) -> ListUrlPriorityResponse:
    """List URL priority rules."""
    log.debug("Listing URL priority rules")

    query = """SELECT category_code, cc, domain, url, priority
               FROM url_priorities FINAL
               ORDER BY category_code, cc, domain, url, priority"""

    try:
        # Execute the SQL query and gather results
        q = query_click(clickhouse, sql.text(query), {})
        rows = list(q)

        # Construct UrlPriority instances from the rows
        url_priorities = [UrlPriority(**row) for row in rows]

        return ListUrlPriorityResponse(rules=url_priorities)
        
    except BaseOONIException as e:
        log.error(f"An error occurred while fetching URL priorities: {e}")
        raise e
    except Exception as e:
        log.error(f"An error occurred while fetching URL priorities: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while fetching URL priorities.")


def initialize_url_priorities_if_needed(clickhouse: ClickhouseDep):
    cntq = "SELECT count() AS cnt FROM url_priorities"
    cnt = query_click_one_row(clickhouse, sql.text(cntq), {})
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
    r = insert_click(clickhouse, query, rows)
    return r


def prepare_url_prio_rule_dict(d: dict):
    # Use an explicit marker "*" to represent "match everything" because NULL
    # cannot be used in UNIQUE constraints; also "IS NULL" is difficult to
    # handle in query generation. See match_prio_rule(...)
    for k in ["category_code", "cc", "domain", "url"]:
        if d.get(k, "") == "":
            d[k] = "*"

    assert sorted(d.keys()) == ["category_code", "cc", "domain", "priority", "url"]


def update_url_priority_click(clickhouse: ClickhouseDep, old: dict, new: dict):
    # The url_priorities table is CollapsingMergeTree
    # Both old and new might be set
    ins_sql = """INSERT INTO url_priorities
        (sign, category_code, cc, domain, url, priority) VALUES
    """
    if old:
        rule = old.copy()
        rule["sign"] = -1 # XXX: sign is not part of the request model but is part of the database
        log.info(f"Deleting prioritization rule {rule}")
        r = insert_click(clickhouse, ins_sql, [rule])
        log.debug(f"Result: {r}")

    if new:
        q = """SELECT count() AS cnt FROM url_priorities FINAL WHERE sign = 1 AND
        category_code = :category_code AND cc = :cc AND domain = :domain
        AND url = :url"""
        cnt = query_click_one_row(clickhouse, sql.text(q), new)
        if cnt and cnt["cnt"] > 0:
            log.info(f"Rejecting duplicate rule {new}")
            raise DuplicateRuleError(err_args=new)

        rule = new.copy()
        rule["sign"] = 1
        log.info(f"Creating prioritization rule {rule}")
        r = insert_click(clickhouse, ins_sql, [rule])
        log.debug(f"Result: {r}")


class UpdateUrlPriorityRequest(BaseModel):
    old_entry: Optional[UrlPriority] = Field(None, description="Existing URL priority rule to update.")
    new_entry: Optional[UrlPriority] = Field(None, description="New URL priority rule to create or replace existing rule.")


@router.post(
    "/_/url-priorities/update",
    tags=["testlists"],
    response_model=int,
    dependencies=[Depends(role_required(["admin"]))],
)
async def post_update_url_priority(
    update: UpdateUrlPriorityRequest,
    clickhouse: ClickhouseDep,
) -> int:
    """Add/update/delete a URL priority rule. An empty old_entry creates a new rule.
    An empty new_entry deletes an existing rule. The current value needs to be sent
    back as "old_entry" to check against race conditions.
    """
    log.info("updating URL priority rule")

    old = update.old_entry.model_dump() if update.old_entry is not None else None
    new = update.new_entry.model_dump() if update.new_entry is not None else None


    if not old and not new:
        raise NoProposedChanges

    if old:
        prepare_url_prio_rule_dict(old)

    if new:
        prepare_url_prio_rule_dict(new)

    try:
        update_url_priority_click(clickhouse, old, new)
        return 1  # Return an integer value
    except BaseOONIException as e:
        log.error(f"An error occurred while updating URL priorities: {e}")
        raise e
    except Exception as e:
        log.error(f"Unexpected error occurred: {e}")
        # Raise a generic HTTPException for unexpected errors
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
