import hashlib
import time
from typing import Optional
from textwrap import dedent

import sqlalchemy as sa
import boto3

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


def hash_email_address(email_address: str, key: str) -> str:
    return hashlib.blake2b(
        email_address.encode(), key=key.encode(), digest_size=16
    ).hexdigest()


def send_login_email(
    destination_address: str, source_address: str, login_url: str, ses_client
) -> str:
    """Format and send a registration/login  email"""
    body_text = dedent(
        f"""
        Welcome to OONI.
        Please login by following {login_url}
        The link can be used on multiple devices and will expire in 24 hours.
        """
    )

    body_html = dedent(
        f"""
        <html>
            <head></head>
            <body>
                <p>Welcome to OONI</p>
                <p>
                    <a href="{login_url}">Please login here</a>
                </p>
                <p>The link can be used on multiple devices and will expire in 24 hours.</p>
            </body>
        </html>
        """
    )

    response = ses_client.send_email(
        Destination={
            "ToAddresses": [
                destination_address,
            ],
        },
        Message={
            "Body": {
                "Html": {
                    "Charset": "UTF-8",
                    "Data": body_html,
                },
                "Text": {
                    "Charset": "UTF-8",
                    "Data": body_text,
                },
            },
            "Subject": {
                "Charset": "UTF-8",
                "Data": "OONI Account activation email",
            },
        },
        Source=source_address,
    )
    return response["MessageId"]
