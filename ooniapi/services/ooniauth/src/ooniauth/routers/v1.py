"""
OONIRun link management

https://github.com/ooni/spec/blob/master/backends/bk-005-ooni-run-v2.md
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse
import logging

import jwt

from fastapi import APIRouter, Depends, Query, HTTPException, Header, Path
from pydantic import Field, validator
from pydantic import EmailStr
from typing_extensions import Annotated

from ..dependencies import get_clickhouse_client, get_ses_client

from ..utils import (
    create_session_token,
    get_account_role,
    hash_email_address,
    send_login_email,
)
from ..common.dependencies import get_settings, role_required
from ..common.config import Settings
from ..common.routers import BaseModel
from ..common.utils import (
    create_jwt,
    decode_jwt,
    get_client_token,
)


log = logging.getLogger(__name__)

router = APIRouter()

# @router.get("/api/v2/ooniauth/user-session")
# @router.post("/api/v2/ooniauth/user-session", response_model=SessionTokenCreate)
# redirect_to: ## Make this optional


class UserRegister(BaseModel):
    email_address: EmailStr = Field(
        title="email address of the user",
        min_length=5,
        max_length=255,
    )
    password: str = Field(title="password of the user", min_length=8)
    redirect_to: Optional[str] = Field(title="redirect to this URL")

    @validator("redirect_to")
    def validate_redirect_to(cls, v):
        # None is also a valid type
        if v is None:
            return v

        u = urlparse(v)
        if u.scheme != "https":
            raise ValueError("Invalid URL")
        valid_dnames = (
            "explorer.ooni.org",
            "explorer.test.ooni.org",
            "run.ooni.io",
            "run.test.ooni.org",
            "test-lists.ooni.org",
            "test-lists.test.ooni.org",
        )
        if u.netloc not in valid_dnames:
            raise ValueError("Invalid URL", u.netloc)

        return v

    @property
    def redirect_to_fqdm(self):
        return urlparse(self.redirect_to).netloc


class UserRegistrationResponse(BaseModel):
    msg: str


@router.post("/v1/user_register", response_model=UserRegistrationResponse)
def user_register(
    user_register: UserRegister,
    settings: Settings = Depends(get_settings),
    ses_client=Depends(get_ses_client),
):
    """Auth Services: start email-based user registration
    ---
    parameters:
      - in: body
        name: register data
        description: Registration data as HTML form or JSON
        required: true
        schema:
          type: object
          properties:
            email_address:
              type: string
            redirect_to: ## Make this optional
              type: string
    responses:
      200:
        description: Confirmation
    """
    email_address = user_register.email_address.lower()

    account_id = hash_email_address(
        email_address=email_address, key=settings.account_id_hashing_key
    )
    now = datetime.now(timezone.utc)
    expiration = now + timedelta(days=1)
    # On the backend side the registration is stateless
    payload = {
        "nbf": now,
        "exp": expiration,
        "aud": "register",
        "account_id": account_id,
        "email_address": email_address,
        "redirect_to": user_register.redirect_to,
    }
    registration_token = create_jwt(payload=payload, key=settings.jwt_encryption_key)

    e = urlparse.urlencode(dict(token=registration_token))
    login_url = urlparse.urlunsplit(
        ("https", user_register.redirect_to_fqdm, "/login", e, "")
    )

    log.info("sending registration token")
    try:
        email_id = send_login_email(
            source_address=settings.email_source_address,
            destination_address=email_address,
            login_url=login_url,
            ses_client=ses_client,
        )
        log.info(f"email sent: {email_id}")
    except Exception as e:
        log.error(e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to send the email")

    return UserRegistrationResponse(msg="ok")


class SessionTokenCreate(BaseModel):
    bearer: str
    redirect_to: str
    email_address: str


@router.get("/v1/user_login", response_model=SessionTokenCreate)
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
    "/v1/user_refresh_token",
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


@router.get("/_/account_metadata")
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
