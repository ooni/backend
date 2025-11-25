import logging

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

# Local imports
from ..common.auth import get_account_id_or_raise
from ..common.dependencies import role_required
from ..common.errors import *
from ..common.routers import BaseModel
from ..common.utils import setnocacheresponse
from ..citizenlab import validate_entry, get_url_list_manager
from ..dependencies import SettingsDep

router = APIRouter(prefix="/v1")

log = logging.getLogger(__name__)


class PullRequestResponse(BaseModel):
    pr_id: str


class Entry(BaseModel):
    category_code: Optional[str] = Field(None, description="Category code of the URL entry.")
    url: Optional[str] = Field(None, description="The URL to be submitted.")
    date_added: Optional[str] = Field(None, description="Date when the entry was added.")
    user: Optional[str] = Field(None, description="User who submitted the entry.")
    notes: Optional[str] = Field(None, description="Any additional notes regarding the entry.")


@router.post(
    "/url-submission/submit",
    tags=["citizenlab"],
    dependencies=[Depends(role_required(["admin", "user"]))],
)
async def post_propose_changes(request: Request, settings: SettingsDep) -> PullRequestResponse:
    """Propose changes: open a Pull Request on GitHub
    ---
    responses:
      200:
        description: Pull request url
        type: object
    """

    try:
        account_id = get_account_id_or_raise(request.Header("authorization"), settings.jwt_encryption_key)
    except Exception:
        raise HTTPException(detail="Authentication required", status_code=401)

    log.info("submitting citizenlab changes")

    try:
        ulm = await get_url_list_manager(settings, account_id)
        pr_id = await ulm.propose_changes(account_id)
        resp = PullRequestResponse(pr_id=pr_id)  # Return the model directly
        setnocacheresponse(resp)
        return resp
    except BaseOONIException as e:
        log.error(f"Exception occurred: {e}")
        raise e  # Already inherits from HTTPException, so can be returned directly
    except Exception as e:
        log.error(f"Unexpected exception occurred: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


class UrlSubmissionUpdateRequest(BaseModel):
    country_code: str = Field(..., description="The country code for the submission.")
    comment: str = Field(..., description="Comment regarding the submission.")
    old_entry: Optional[Entry] = Field(None, description="The old entry to validate against.")
    new_entry: Optional[Entry] = Field(None, description="New entry to create or update.")


class UrlSubmissionResponse(BaseModel):
    updated_entry: Optional[Entry] = Field(None, description="The updated URL entry after processing.")


@router.post(
    "/url-submission/update-url",
    tags=["citizenlab"],
    dependencies=[Depends(role_required(["admin", "user"]))],
)
async def url_submission_update_url(settings: SettingsDep, request: Request, update: UrlSubmissionUpdateRequest):
    """Create/update/delete a CitizenLab URL entry. The current value must
    be sent back as "old_entry" to check against race conditions.
    Empty old_entry means creating a new rule. Empty new_entry means deleting an existing rule.
    """

    try:
        account_id = get_account_id_or_raise(request.Header("authorization"), settings.jwt_encryption_key)
    except Exception:
        raise HTTPException(detail="Authentication required", status_code=401)

    ulm = get_url_list_manager(settings, account_id)

    new = update.new_entry.model_dump()
    old = update.old_entry.model_dump()

    try:
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
        setnocacheresponse(resp)
        return resp
    except BaseOONIException as e:
        log.error(f"OONIException occurred: {e}")
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
