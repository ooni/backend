import time
from typing import List, Optional
from textwrap import dedent
from urllib.parse import urlencode, urlparse, urlunsplit

import sqlalchemy as sa

from .common.utils import create_jwt

VALID_REDIRECT_TO_FQDN = (
    "explorer.ooni.org",
    "explorer.test.ooni.org",
    "run.ooni.io",
    "run.test.ooni.org",
    "test-lists.ooni.org",
    "test-lists.test.ooni.org",
)


def format_login_url(redirect_to: str, registration_token: str) -> str:
    login_fqdm = urlparse(redirect_to).netloc
    e = urlencode(dict(token=registration_token))
    return urlunsplit(("https", login_fqdm, "/login", e, ""))


def create_session_token(
    key: str,
    email_address: str,
    role: str,
    session_expiry_days: int,
    login_expiry_days: int,
    login_time: Optional[int] = None,
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
        "login_time": login_time,
        "role": role,
        "email_address": email_address,
    }
    return create_jwt(payload=payload, key=key)


def get_account_role(admin_emails: List[str], email_address: str) -> str:
    if email_address in admin_emails:
        return "admin"
    return "user"


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
