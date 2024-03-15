"""
OONIRun link management

https://github.com/ooni/spec/blob/master/backends/bk-005-ooni-run-v2.md
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse
import logging

import jwt

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import Field, validator
from pydantic import EmailStr
from typing_extensions import Annotated

from ..dependencies import get_clickhouse_client, get_ses_client

from ..utils import (
    create_session_token,
    get_account_role,
    hash_email_address,
    send_login_email,
    format_login_url,
    VALID_REDIRECT_TO_FQDN,
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


class CreateUserLogin(BaseModel):
    email_address: EmailStr = Field(
        title="email address of the user",
        min_length=5,
        max_length=255,
    )
    redirect_to: str = Field(title="redirect to this URL")

    @validator("redirect_to")
    def validate_redirect_to(cls, v):
        u = urlparse(v)
        if u.scheme != "https":
            raise ValueError("Invalid URL")

        if u.netloc not in VALID_REDIRECT_TO_FQDN:
            raise ValueError("Invalid URL", u.netloc)

        return v


class UserLogin(BaseModel):
    email_address: str
    login_token_expiration: datetime


@router.post("/v2/ooniauth/user-login", response_model=UserLogin)
async def create_user_login(
    req: CreateUserLogin,
    settings: Settings = Depends(get_settings),
    ses_client=Depends(get_ses_client),
):
    """Auth Services: login by receiving an email"""
    email_address = req.email_address.lower()

    account_id = hash_email_address(
        email_address=email_address, key=settings.account_id_hashing_key
    )
    now = datetime.now(timezone.utc)
    login_token_expiration = now + timedelta(days=1)
    # On the backend side the registration is stateless
    payload = {
        "nbf": now,
        "exp": login_token_expiration,
        "aud": "register",
        "account_id": account_id,
        "email_address": email_address,
        "redirect_to": req.redirect_to,
    }
    registration_token = create_jwt(payload=payload, key=settings.jwt_encryption_key)

    login_url = format_login_url(
        redirect_to=req.redirect_to, registration_token=registration_token
    )
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

    return UserLogin(
        email_address=email_address,
        login_token_expiration=login_token_expiration,
    )


class UserSession(BaseModel):
    account_id: str
    session_token: str
    redirect_to: str
    email_address: str
    role: str
    login_time: Optional[datetime]
    is_logged_in: bool = False


def maybe_get_user_session_from_header(
    db, authorization_header: str, jwt_encryption_key: str
) -> Optional[UserSession]:
    token = get_client_token(
        authorization=authorization_header, jwt_encryption_key=jwt_encryption_key
    )
    if token is None:
        return None

    account_id = token["account_id"]
    role = get_account_role(account_id=account_id, db=db) or "user"
    login_time = datetime.fromtimestamp(token["login_time"])
    email_address = token["email_address"]
    redirect_to = ""

    return UserSession(
        session_token="",
        redirect_to=redirect_to,
        email_address=email_address,
        role=role,
        login_time=login_time,
        account_id=account_id,
        is_logged_in=True,
    )


def get_user_session_from_login_token(
    login_token: str, db, jwt_encryption_key: str
) -> UserSession:
    try:
        d = decode_jwt(
            token=login_token,
            key=jwt_encryption_key,
            audience="register",
        )
        account_id = d["account_id"]
        role = get_account_role(db=db, account_id=account_id) or "user"
        return UserSession(
            session_token="",
            redirect_to=d["redirect_to"],
            email_address=d["email_address"],
            role=role,
            login_time=datetime.now(timezone.utc),
            account_id=account_id,
        )
    except (
        jwt.exceptions.MissingRequiredClaimError,
        jwt.exceptions.InvalidSignatureError,
        jwt.exceptions.DecodeError,
    ):
        raise HTTPException(401, "Invalid credentials")
    except jwt.exceptions.ExpiredSignatureError:
        raise HTTPException(401, "Expired token")


class CreateUserSession(BaseModel):
    login_token: Optional[str] = Field(
        title="login token that was received via email", default=None
    )


@router.post("/v2/ooniauth/user-session", response_model=UserSession)
async def create_user_session(
    req: Optional[CreateUserSession] = None,
    authorization: str = Header("authorization"),
    settings: Settings = Depends(get_settings),
    db: Settings = Depends(get_clickhouse_client),
):
    """Auth Services: login using a registration/login link"""
    if req and req.login_token:
        user_session = get_user_session_from_login_token(
            login_token=req.login_token,
            db=db,
            jwt_encryption_key=settings.jwt_encryption_key,
        )
    else:
        user_session = maybe_get_user_session_from_header(
            authorization_header=authorization,
            db=db,
            jwt_encryption_key=settings.jwt_encryption_key,
        )

    if not user_session:
        raise HTTPException(401, "no valid session found")

    assert user_session.login_time
    user_session.session_token = create_session_token(
        key=settings.jwt_encryption_key,
        account_id=user_session.account_id,
        role=user_session.role,
        session_expiry_days=settings.session_expiry_days,
        login_expiry_days=settings.login_expiry_days,
        login_time=int(user_session.login_time.timestamp()),
        email_address=user_session.email_address,
    )
    user_session.is_logged_in = True
    return user_session


@router.get("/v2/ooniauth/user-session", response_model=UserSession)
async def get_user_session(
    authorization: str = Header("authorization"),
    settings: Settings = Depends(get_settings),
    db: Settings = Depends(get_clickhouse_client),
):
    user_session = maybe_get_user_session_from_header(
        authorization_header=authorization,
        db=db,
        jwt_encryption_key=settings.jwt_encryption_key,
    )
    if not user_session:
        return UserSession(
            session_token="",
            redirect_to="",
            email_address="",
            role="",
            login_time=None,
            account_id="",
            is_logged_in=False,
        )
    return user_session
