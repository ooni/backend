import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field

# Local imports
from citizenlab.common.auth import get_account_id_or_raise
from citizenlab.common.dependencies import role_required
from citizenlab.common.errors import *
from citizenlab.common.routers import BaseModel
from citizenlab.common.utils import setnocacheresponse
from citizenlab.dependencies import SettingsDep
from citizenlab.manager import validate_entry, get_url_list_manager
from citizenlab.models import UrlSubmissionUpdateRequest, UrlSubmissionResponse, PullRequestResponse

router = APIRouter(prefix="/v1")

log = logging.getLogger(__name__)


@router.post(
    "/url-submission/submit",
    tags=["citizenlab"],
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

    log.info("submitting citizenlab changes")

    try:
        ulm = await get_url_list_manager(settings, account_id)
        pr_id = await ulm.propose_changes(account_id)
        resp = PullRequestResponse(pr_id=pr_id)  # Return the model directly
        setnocacheresponse(response)
        return resp
    except BaseOONIException as e:
        log.error(f"Exception occurred: {e}")
        raise e  # Already inherits from HTTPException, so can be returned directly
    except Exception as e:
        log.error(f"Unexpected exception occurred: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post(
    "/url-submission/update-url",
    tags=["citizenlab"],
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

    ulm = get_url_list_manager(settings, account_id)

    new = update.new_entry.model_dump() if update.new_entry is not None else None
    old = update.old_entry.model_dump() if update.old_entry is not None else None

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
        setnocacheresponse(response)
        return resp
    except BaseOONIException as e:
        log.error(f"OONIException occurred: {e}")
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
