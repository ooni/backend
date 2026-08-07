import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field
from typing import Optional

# Local imports
from testlists.common.auth import get_account_id_or_raise
from testlists.common.dependencies import role_required, SettingsDep
from testlists.common.errors import *
from testlists.common.routers import BaseModel
from testlists.common.utils import setnocacheresponse
from testlists.manager import validate_entry, get_url_list_manager

router = APIRouter(prefix="/v1")

log = logging.getLogger(__name__)


class PullRequestResponse(BaseModel):
    pr_id: str


@router.post(
    "/url-submission/submit",
    tags=["testlists"],
    dependencies=[Depends(role_required(["admin", "user"]))],
)
async def post_propose_changes(
    request: Request,
    response: Response,
    settings: SettingsDep
    ) -> PullRequestResponse:
    """Propose changes: open a Pull Request on GitHub
    ---
    responses:
      200:
        description: Pull request url
        type: object
    """

    try:
        account_id = get_account_id_or_raise(request.headers.get("Authorization"), settings.jwt_encryption_key)
    except Exception:
        raise HTTPException(detail="Authentication required", status_code=401)

    log.info("submitting testlists changes")

    ulm = None
    try:
        ulm = get_url_list_manager(settings, account_id)
        pr_id = ulm.propose_changes(account_id)
        resp = PullRequestResponse(pr_id=pr_id)  # Return the model directly
        setnocacheresponse(response)
        return resp
    except BaseOONIException as e:
        log.error(f"Exception occurred: {e}")
        raise e  # Already inherits from HTTPException, so can be returned directly
    except Exception as e:
        log.exception(f"Unexpected exception occurred: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        # Deterministically release the per-account FileLock regardless of
        # success/failure - see URLListManager.close() docstring for why
        # relying on `del ulm` + gc.collect() only on the success path
        # caused cascading FileLock timeouts on unrelated requests in
        # production.
        if ulm is not None:
            ulm.close()


class Entry(BaseModel):
    category_code: str = Field(description="Category code of the URL entry.")
    url: Optional[str] = Field("", description="The URL to be submitted.")
    date_added: str = Field(description="Date when the entry was added.")
    notes: str = Field(description="Any additional notes regarding the entry.")
    source: str = Field(description="Any additional notes regarding the entry.")


class UrlSubmissionUpdateRequest(BaseModel):
    country_code: str = Field(..., description="The country code for the submission.")
    comment: str = Field(..., description="Comment regarding the submission.")
    old_entry: Optional[Entry] = Field(None, description="The old entry to validate against.")
    new_entry: Optional[Entry] = Field(None, description="New entry to create or update.")


class UrlSubmissionResponse(BaseModel):
    updated_entry: Optional[Entry] = Field(None, description="The updated URL entry after processing.")


@router.post(
    "/url-submission/update-url",
    tags=["testlists"],
    dependencies=[Depends(role_required(["admin", "user"]))],
)
async def url_submission_update_url(
    settings: SettingsDep,
    request: Request,
    response: Response,
    update: UrlSubmissionUpdateRequest
    ) -> UrlSubmissionResponse:
    """Create/update/delete a CitizenLab URL entry. The current value must
    be sent back as "old_entry" to check against race conditions.
    Empty old_entry means creating a new rule. Empty new_entry means deleting an existing rule.
    """

    try:
        account_id = get_account_id_or_raise(request.headers.get("Authorization"), settings.jwt_encryption_key)
    except Exception:
        raise HTTPException(detail="Authentication required", status_code=401)

    new = update.new_entry.model_dump() if update.new_entry is not None else None
    old = update.old_entry.model_dump() if update.old_entry is not None else None

    ulm = None
    try:
        ulm = get_url_list_manager(settings, account_id)

        if new:
            validate_entry(new)
        if old:
            validate_entry(old)

        ulm.update(
            account_id=account_id,
            cc=update.country_code,
            old_entry=old,
            new_entry=new,
            comment=update.comment,
        )
        resp = UrlSubmissionResponse(updated_entry=new)
        setnocacheresponse(response)
        return resp
    except BaseOONIException as e:
        log.error(f"OONIException occurred: {e}")
        raise e
    except Exception as e:
        # NOTE: this used to swallow the exception without logging it at
        # all, so any failure inside ulm.update() - including dulwich
        # errors from git.add()/git.commit() - was only ever visible to
        # the caller as a terse HTTP 400 with str(e) as the body, with
        # zero trace of it in the server logs. Log the full traceback so
        # these are actually debuggable.
        log.exception(
            f"Unexpected exception occurred while updating url-submission "
            f"for account_id={account_id}: {e}"
        )
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        # See URLListManager.close() docstring: without this, an
        # exception here left the account's FileLock held until an
        # unrelated request elsewhere happened to force a full GC pass,
        # causing every other request for this account_id (even plain
        # reads) to fail with a FileLock timeout in the meantime.
        if ulm is not None:
            ulm.close()
