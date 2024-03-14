import time
import sqlalchemy as sa
from typing import Optional
from .common.utils import create_jwt, query_click_one_row


def create_session_token(
    key: str,
    account_id: str,
    role: str,
    session_expiry_days: int,
    login_expiry_days: int,
    login_time=None,
) -> str:
    now = int(time.time())
    session_exp = now + session_expiry_days * 86400
    if login_time is None:
        login_time = now
    login_exp = login_time + login_expiry_days * 86400
    exp = min(session_exp, login_exp)
    payload = {
        "nbf": now,
        "iat": now,
        "exp": exp,
        "aud": "user_auth",
        "account_id": account_id,
        "login_time": login_time,
        "role": role,
    }
    return create_jwt(payload=payload, key=key)


def get_account_role(db, account_id: str) -> Optional[str]:
    """Get account role from database, or None"""
    query = "SELECT role FROM accounts WHERE account_id = :account_id"
    query_params = dict(account_id=account_id)
    r = query_click_one_row(db, sa.text(query), query_params)
    return r["role"] if r else None
