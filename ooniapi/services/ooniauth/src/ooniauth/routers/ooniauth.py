"""
OONIRun link management

https://github.com/ooni/spec/blob/master/backends/bk-005-ooni-run-v2.md
"""

from datetime import datetime, timedelta, timezone, date
from typing import Dict, List, Optional, Tuple
import logging
import jwt

import sqlalchemy as sa
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query, HTTPException, Header, Path
from pydantic import computed_field, Field, validator
from pydantic import BaseModel as PydandicBaseModel
from typing_extensions import Annotated

from ..dependencies import get_clickhouse_client

from ..utils import create_session_token, get_account_role
from ..common.dependencies import get_settings, role_required
from ..common.config import Settings
from ..common.routers import BaseModel
from ..common.utils import (
    decode_jwt,
    get_client_role,
    get_client_token,
    get_account_id_or_raise,
    get_account_id_or_none,
)


log = logging.getLogger(__name__)

router = APIRouter()


class SessionTokenCreate(BaseModel):
    bearer: str
    redirect_to: str
    email_address: str


@router.get("/api/v1/user_login", response_model=SessionTokenCreate)
def user_login(
    token: Annotated[
        str,
        Query(alias="k", description="JWT token with aud=register"),
    ],
    settings: Settings = Depends(get_settings),
    db: Settings = Depends(get_clickhouse_client),
):
    """Auth Services: login using a registration/login link"""
    try:
        dec = decode_jwt(
            token=token, key=settings.jwt_encryption_key, audience="register"
        )
    except jwt.exceptions.MissingRequiredClaimError:
        raise HTTPException(401, "Invalid token")
    except jwt.exceptions.InvalidSignatureError:
        raise HTTPException(401, "Invalid credential signature")
    except jwt.exceptions.DecodeError:
        raise HTTPException(401, "Invalid credentials")
    except jwt.exceptions.ExpiredSignatureError:
        raise HTTPException(401, "Expired token")

    log.info("user login successful")

    # Store account role in token to prevent frequent DB lookups
    role = get_account_role(db=db, account_id=dec["account_id"]) or "user"
    redirect_to = dec.get("redirect_to", "")
    email = dec["email_address"]

    token = create_session_token(
        key=settings.jwt_encryption_key,
        account_id=dec["account_id"],
        role=role,
        session_expiry_days=settings.session_expiry_days,
        login_expiry_days=settings.login_expiry_days,
    )
    return SessionTokenCreate(
        bearer=token,
        redirect_to=redirect_to,
        email_address=email,
    )


class SessionTokenRefresh(BaseModel):
    bearer: str


@router.get(
    "/api/v1/user_refresh_token",
    dependencies=[Depends(role_required(["admin", "user"]))],
    response_model=SessionTokenRefresh,
)
def user_refresh_token(
    settings: Settings = Depends(get_settings),
    authorization: str = Header("authorization"),
):
    """Auth services: refresh user token
    ---
    responses:
      200:
        description: JSON with "bearer" key
    """
    tok = get_client_token(
        authorization=authorization, jwt_encryption_key=settings.jwt_encryption_key
    )

    # @role_required already checked for expunged tokens
    if not tok:
        raise HTTPException(401, "Invalid credentials")

    newtoken = create_session_token(
        key=settings.jwt_encryption_key,
        account_id=tok["account_id"],
        role=tok["role"],
        session_expiry_days=settings.session_expiry_days,
        login_expiry_days=settings.login_expiry_days,
        login_time=tok["login_time"],
    )
    log.debug("user token refresh successful")
    return SessionTokenRefresh(bearer=newtoken)


class AccountMetadata(BaseModel):
    logged_in: bool
    role: str


# @cross_origin(origins=origins, supports_credentials=True)
@router.get("/api/_/account_metadata")
def get_account_metadata(
    settings: Settings = Depends(get_settings),
    authorization: str = Header("authorization"),
):
    """Get account metadata for logged-in users
    ---
    responses:
      200:
        description: Username and role if logged in.
        schema:
          type: object
    """
    try:
        tok = get_client_token(
            authorization=authorization, jwt_encryption_key=settings.jwt_encryption_key
        )
        if not tok:
            raise HTTPException(401, "Invalid credentials")
        return AccountMetadata(logged_in=True, role=tok["role"])
    except Exception:
        raise HTTPException(401, "Invalid credentials")


# def _set_account_role(email_address, role: str) -> int:
#     log = current_app.logger
#     account_id = hash_email_address(email_address)
#     # log.info(f"Giving account {account_id} role {role}")
#     # TODO: when role is changed enforce token expunge
#     query_params = dict(account_id=account_id, role=role)
#     log.info("Creating/Updating account role")
#     # 'accounts' is on RocksDB (ACID key-value database)
#     query = """INSERT INTO accounts (account_id, role) VALUES"""
#     return insert_click(query, [query_params])
# @router.get("/api/v1/get_account_role/<email_address>")
# # @role_required("admin")
# def admin_get_account_role(email_address) -> Response:
#     """Get account role. Return an error message if the account is not found.
#     Only for admins.
#     ---
#     security:
#       cookieAuth:
#         type: JWT
#         in: cookie
#         name: ooni
#     parameters:
#       - name: email_address
#         in: path
#         required: true
#         type: string
#     responses:
#       200:
#         description: Role or error message
#         schema:
#           type: object
#     """
#     log = current_app.logger
#     email_address = email_address.strip().lower()
#     if EMAIL_RE.fullmatch(email_address) is None:
#         return jerror("Invalid email address")
#     account_id = hash_email_address(email_address)
#     role = _get_account_role(account_id)
#     if role is None:
#         log.info(f"Getting account {account_id} role: not found")
#         return jerror("Account not found")

#     log.info(f"Getting account {account_id} role: {role}")
#     return nocachejson(role=role)


# @auth_blueprint.route("/api/v1/set_session_expunge", methods=["POST"])
# # @role_required("admin")
# def admin_set_session_expunge() -> Response:
#     """Force refreshing all session tokens for a given account.
#     Only for admins.
#     ---
#     security:
#       cookieAuth:
#         type: JWT
#         in: cookie
#         name: ooni
#     parameters:
#       - in: body
#         name: email address
#         description: data as HTML form or JSON
#         required: true
#         schema:
#           type: object
#           properties:
#             email_address:
#               type: string
#     responses:
#       200:
#         description: Confirmation
#     """
#     log = current_app.logger
#     req = request.json if request.is_json else request.form
#     assert req
#     email_address = req.get("email_address", "").strip().lower()
#     if EMAIL_RE.fullmatch(email_address) is None:
#         return jerror("Invalid email address")
#     account_id = hash_email_address(email_address)
#     log.info(f"Setting expunge for account {account_id}")
#     # If an entry is already in place update the threshold as the new
#     # value is going to be safer
#     # 'session_expunge' is on RocksDB (ACID key-value database)
#     log.info("Inserting into Clickhouse session_expunge")
#     query = "INSERT INTO session_expunge (account_id) VALUES"
#     query_params: Any = dict(account_id=account_id)
#     # the `threshold` column defaults to the current time
#     insert_click(query, [query_params])
#     return nocachejson()

# @auth_blueprint.route("/api/v1/set_account_role", methods=["POST"])
# @role_required("admin")
# def set_account_role() -> Response:
#     """Set a role to a given account identified by an email address.
#     Only for admins.
#     ---
#     security:
#       cookieAuth:
#         type: JWT
#         in: cookie
#         name: ooni
#     parameters:
#       - in: body
#         name: email address and role
#         description: data as HTML form or JSON
#         required: true
#         schema:
#           type: object
#           properties:
#             email_address:
#               type: string
#             role:
#               type: string
#     responses:
#       200:
#         description: Confirmation
#     """
#     log = current_app.logger
#     req = request.json if request.is_json else request.form
#     assert req
#     role = req.get("role", "").strip().lower()
#     email_address = req.get("email_address", "").strip().lower()
#     if EMAIL_RE.fullmatch(email_address) is None:
#         return jerror("Invalid email address")
#     if role not in ["user", "admin"]:
#         return jerror("Invalid role")

#     r = _set_account_role(email_address, role)
#     log.info(f"Role set {r}")
#     return nocachejson()
