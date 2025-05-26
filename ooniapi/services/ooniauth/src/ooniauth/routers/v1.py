from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse, urlencode, urlunsplit
import logging

import jwt

from fastapi import APIRouter, Depends, Query, HTTPException, Header, Path
from pydantic import Field
from pydantic.functional_validators import field_validator
from pydantic import EmailStr
from typing_extensions import Annotated

from ..dependencies import get_ses_client

from ..utils import (
    create_session_token,
    get_account_role,
    send_login_email,
    format_login_url,
    VALID_REDIRECT_TO_FQDN,
)
from ..common.dependencies import get_settings, role_required
from ..common.config import Settings
from ..common.routers import BaseModel
from ..common.auth import (
    create_jwt,
    decode_jwt,
    get_client_token,
)


log = logging.getLogger(__name__)

router = APIRouter()


class UserRegister(BaseModel):
    email_address: EmailStr = Field(
        title="email address of the user",
        min_length=5,
        max_length=255,
    )
    redirect_to: str = Field(title="redirect to this URL")

    @field_validator("redirect_to")
    def validate_redirect_to(cls, v):
        u = urlparse(v)
        if u.scheme != "https":
            raise ValueError("Invalid URL")

        if u.netloc not in VALID_REDIRECT_TO_FQDN:
            raise ValueError("Invalid URL", u.netloc)

        return v


class UserRegistrationResponse(BaseModel):
    msg: str


@router.post("/v1/user_register", response_model=UserRegistrationResponse)
async def user_register(
    user_register: UserRegister,
    settings: Settings = Depends(get_settings),
    ses_client=Depends(get_ses_client),
):
    """Auth Services: start email-based user registration"""
    email_address = user_register.email_address.lower()

    now = datetime.now(timezone.utc)
    expiration = now + timedelta(days=1)
    # On the backend side the registration is stateless
    payload = {
        "nbf": now,
        "exp": expiration,
        "aud": "register",
        "email_address": email_address,
        "redirect_to": user_register.redirect_to,
    }
    registration_token = create_jwt(payload=payload, key=settings.jwt_encryption_key)

    login_url = format_login_url(
        redirect_to=user_register.redirect_to, registration_token=registration_token
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
async def user_login(
    token: Annotated[
        str,
        Query(alias="k", description="JWT token with aud=register"),
    ],
    settings: Settings = Depends(get_settings),
):
    """Auth Services: login using a registration/login link"""

    # **IMPORTANT** You have to compute this token using a different key
    # to the one used in ooniprobe service, because you could allow
    # a login bypass attack if you don't. 
    #
    # The token used in ooniprobe is generated regardless of any authentication,
    # because it's a toy token to please old probes. 
    #
    # We set this up in terraform

    try:
        dec = decode_jwt(
            token=token, key=settings.jwt_encryption_key, audience="register"
        )
    except (
        jwt.exceptions.MissingRequiredClaimError,
        jwt.exceptions.InvalidSignatureError,
        jwt.exceptions.DecodeError,
    ):
        raise HTTPException(401, "Invalid credentials")
    except jwt.exceptions.ExpiredSignatureError:
        raise HTTPException(401, "Expired token")

    log.info("user login successful")

    # Store account role in token to prevent frequent DB lookups
    email_address = dec["email_address"]
    role = get_account_role(
        admin_emails=settings.admin_emails, email_address=email_address
    )
    redirect_to = dec.get("redirect_to", "")

    token = create_session_token(
        key=settings.jwt_encryption_key,
        hashing_key=settings.account_id_hashing_key,
        email_address=email_address,
        role=role,
        session_expiry_days=settings.session_expiry_days,
        login_expiry_days=settings.login_expiry_days,
    )
    return SessionTokenCreate(
        bearer=token,
        redirect_to=redirect_to,
        email_address=email_address,
    )


class SessionTokenRefresh(BaseModel):
    bearer: str


@router.get(
    "/v1/user_refresh_token",
    dependencies=[Depends(role_required(["admin", "user"]))],
    response_model=SessionTokenRefresh,
)
async def user_refresh_token(
    settings: Settings = Depends(get_settings),
    authorization: str = Header("authorization"),
):
    """Auth services: refresh user token"""
    tok = get_client_token(
        authorization=authorization, jwt_encryption_key=settings.jwt_encryption_key
    )

    # @role_required already checked for validity of token
    assert tok is not None

    newtoken = create_session_token(
        key=settings.jwt_encryption_key,
        hashing_key=settings.account_id_hashing_key,
        email_address=tok["email_address"],
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
async def get_account_metadata(
    settings: Settings = Depends(get_settings),
    authorization: str = Header("authorization"),
):
    """Get account metadata for logged-in users"""
    try:
        tok = get_client_token(
            authorization=authorization, jwt_encryption_key=settings.jwt_encryption_key
        )
        return AccountMetadata(logged_in=True, role=tok["role"])
    except:
        return AccountMetadata(logged_in=False, role="")
