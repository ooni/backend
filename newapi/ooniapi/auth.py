"""
Authentication API
"""
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
import urllib.parse as urlp
from typing import Optional, Dict, Any, Tuple
import hashlib
import re
import smtplib
import time

from flask import Blueprint, current_app, request, make_response, Response
from flask.json import jsonify
from flask_cors import cross_origin
from sqlalchemy import sql
import jwt  # debdeps: python3-jwt
import jwt.exceptions  # debdeps: python3-jwt

from ooniapi.config import metrics
from ooniapi.database import query_click_one_row, insert_click
from ooniapi.utils import nocachejson, jerror

origins = [
    re.compile(r"^https://[-A-Za-z0-9]+\.ooni\.org$"),
    re.compile(r"^https://[-A-Za-z0-9]+\.test\.ooni\.org$"),
    re.compile(r"^https://[-A-Za-z0-9]+\.ooni\.io$"),
    re.compile(r"^https://[-A-Za-z0-9]+\.test\.ooni\.io$"),
]
auth_blueprint = Blueprint("auth_api", "auth")

"""
Browser authentication - see probe_services.py for probe authentication
Requirements:
  - Never store users email address nor IP addresses nor passwords
  - Verify email to limit spambots. Do not use CAPCHAs
  - Support multiple sessions / devices, ability to register/login again
  - Do not leak the existence/absence of accounts with a given login or email

Workflow:
  Explorer:
    - call user_register using an email and receive a temporary login link
    - call login_user and receive a long-lived cookie
    - call <TODO> using the previous email to get a new temp. login link
    - call the citizenlab CRUD entry points using the cookie
    - call bookmarked searches/urls/msmts entry points using the cookie

Configuration parameters:
    BASE_URL
    JWT_ENCRYPTION_KEY
    MAIL_SERVER
    MAIL_PORT
    MAIL_USERNAME
    MAIL_PASSWORD
    MAIL_USE_SSL
    MAIL_SOURCE_ADDRESS
    LOGIN_EXPIRY_DAYS
    SESSION_EXPIRY_DAYS
"""

# Courtesy of https://emailregex.com/
EMAIL_RE = re.compile(r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)")


def create_jwt(payload: dict) -> str:
    key = current_app.config["JWT_ENCRYPTION_KEY"]
    token = jwt.encode(payload, key, algorithm="HS256")
    if isinstance(token, bytes):
        return token.decode()
    else:
        return token


def decode_jwt(token, **kw):
    key = current_app.config["JWT_ENCRYPTION_KEY"]
    return jwt.decode(token, key, algorithms=["HS256"], **kw)


def hash_email_address(email_address: str) -> str:
    key = current_app.config["JWT_ENCRYPTION_KEY"].encode()
    em = email_address.encode()
    return hashlib.blake2b(em, key=key, digest_size=16).hexdigest()


def set_JWT_cookie(res, token: str) -> None:
    """Set/overwrite the "ooni" cookie in the browser:
    - secure: used only on HTTPS
    - httponly: block javascript in the browser from accessing it
    """
    # https://github.com/pallets/werkzeug/issues/1549
    # res.set_cookie("ooni", token, secure=True, httponly=True)
    cookie = f"ooni={token}; Secure; HttpOnly; SameSite=None; Path=/"
    res.headers.add("Set-Cookie", cookie)


def role_required(roles):
    # Decorator requiring user to be logged in and have the right role.
    # Also:
    #  refreshes the session cookie if needed
    #  explicitely set no-cache headers
    #  apply the cross_origin decorator to:
    #    - set CORS header to a trusted URL
    #    - enable credentials (cookies)
    #
    if isinstance(roles, str):
        roles = [roles]

    def decorator(func):
        @cross_origin(origins=origins, supports_credentials=True)
        @wraps(func)
        def wrapper(*args, **kwargs):
            token = request.cookies.get("ooni", "")
            try:
                tok = decode_jwt(token, audience="user_auth")
                del token
                if tok["role"] not in roles:
                    return jerror("Role not authorized", 401)
            except Exception:
                return jerror("Authentication required", 401)

            # check for session expunge
            # TODO: cache query?
            query = """SELECT threshold
                FROM session_expunge
                WHERE account_id = :account_id """
            account_id = tok["account_id"]
            query_params = dict(account_id=account_id)
            row = query_click_one_row(sql.text(query), query_params)
            if row:
                threshold = row["threshold"]
                iat = datetime.utcfromtimestamp(tok["iat"])
                print((iat, threshold))
                if iat < threshold:
                    return jerror("Authentication token expired", 401)

            # attach account_id to request
            request._account_id = account_id
            # run the HTTP route method
            resp = func(*args, **kwargs)
            # Prevent an authenticated page to be cached and served to
            # unauthorized users
            resp.cache_control.no_cache = True

            token_age = time.time() - tok["iat"]
            if token_age > 600:  # refresh token if needed
                newtoken = _create_session_token(
                    tok["account_id"], tok["role"], tok["login_time"]
                )
                set_JWT_cookie(resp, newtoken)

            return resp

        return wrapper

    return decorator


def get_account_id_or_none() -> Optional[str]:
    try:
        token = request.cookies.get("ooni", "")
        tok = decode_jwt(token, audience="user_auth")
    except Exception:
        return None

    return tok["account_id"]


def get_account_id() -> str:
    try:
        token = request.cookies.get("ooni", "")
        tok = decode_jwt(token, audience="user_auth")
    except Exception:
        return jerror("Authentication required", 401)

    return tok["account_id"]


def _send_email(dest_addr: str, msg: EmailMessage) -> None:
    log = current_app.logger
    conf = current_app.config
    smtphost = conf["MAIL_SERVER"]
    port = conf["MAIL_PORT"]
    mail_user = conf["MAIL_USERNAME"]
    mail_password = conf["MAIL_PASSWORD"]
    use_ssl = conf["MAIL_USE_SSL"]
    log.debug(f"connecting to {smtphost}:{port} as {mail_user}")
    SMTP = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    try:
        with SMTP(host=smtphost, port=port) as s:
            s.ehlo()
            s.login(mail_user, mail_password)
            s.send_message(msg)
    except Exception as e:
        log.error(e, exc_info=True)
        raise


def send_login_email(dest_addr: str, login_url: str) -> None:
    """Format and send a registration/login  email"""
    src_addr = current_app.config["MAIL_SOURCE_ADDRESS"]

    msg = EmailMessage()
    msg["Subject"] = "OONI Account activation"
    msg["From"] = src_addr
    msg["To"] = dest_addr

    txt = f"""Welcome to OONI.

    Please login by following {login_url}

    The link can be used on multiple devices and will expire in 24 hours.
    """
    msg.set_content(txt)
    html = f"""\
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
    msg.add_alternative(html, subtype="html")
    _send_email(dest_addr, msg)


def validate_redirect_url(rt_url: str) -> Tuple[str, str]:
    """Validates the redirect_to URL used in registration, rebuilds it
    and return the FQDN"""
    u = urlp.urlparse(rt_url)
    if not (u.scheme == "https" and u.netloc.endswith(".ooni.org")):
        raise ValueError("Invalid URL")
    dn = u.netloc[:-9]  # without .ooni.org
    valid_dnames = ("explorer", "explorer.test", "test-lists", "test-lists.test")
    if dn not in valid_dnames:
        raise ValueError("Invalid URL", dn)

    return u.geturl(), u.netloc


@metrics.timer("user_register")
@auth_blueprint.route("/api/v1/user_register", methods=["POST"])
@cross_origin(origins=origins, supports_credentials=True)
def user_register() -> Response:
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
            redirect_to:
              type: string
    responses:
      200:
        description: Confirmation
    """
    log = current_app.logger
    req = request.json if request.is_json else request.form
    email_address = req.get("email_address", "").strip().lower()
    if not email_address:
        return jerror("Invalid request")
    if EMAIL_RE.fullmatch(email_address) is None:
        return jerror("Invalid email address")

    redirect_to = req.get("redirect_to", "").strip()
    try:
        redirect_to, login_fqdn = validate_redirect_url(redirect_to)
    except Exception:
        return jerror("Invalid request")

    account_id = hash_email_address(email_address)
    now = datetime.utcnow()
    expiration = now + timedelta(days=1)
    # On the backend side the registration is stateless
    payload = {
        "nbf": now,
        "exp": expiration,
        "aud": "register",
        "account_id": account_id,
        "redirect_to": redirect_to,
    }
    registration_token = create_jwt(payload)

    e = urlp.urlencode(dict(token=registration_token))
    login_url = urlp.urlunsplit(("https", login_fqdn, "/login", e, ""))

    log.info("sending registration token")
    try:
        send_login_email(email_address, login_url)
        log.info("email sent")
    except Exception as e:
        log.error(e, exc_info=True)
        return jerror("Unable to send the email")

    return nocachejson(msg="ok")


def _create_session_token(account_id: str, role: str, login_time=None) -> str:
    now = int(time.time())
    session_exp = now + current_app.config["SESSION_EXPIRY_DAYS"] * 86400
    if login_time is None:
        login_time = now
    login_exp = login_time + current_app.config["LOGIN_EXPIRY_DAYS"] * 86400
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
    return create_jwt(payload)


@metrics.timer("user_login")
@auth_blueprint.route("/api/v1/user_login", methods=["GET"])
@cross_origin(origins=origins, supports_credentials=True)
def user_login() -> Response:
    """Probe Services: login using a registration/login link
    ---
    parameters:
      - name: k
        in: query
        type: string
        description: JWT token with aud=register
    responses:
      200:
        description: JSON with "redirect_to" or "msg" key; set cookie
    """
    log = current_app.logger
    token = request.args.get("k", "")
    try:
        dec = decode_jwt(token, audience="register")
    except jwt.exceptions.MissingRequiredClaimError:
        return jerror("Invalid token type", code=401)
    except jwt.exceptions.InvalidSignatureError:
        return jerror("Invalid credential signature", code=401)
    except jwt.exceptions.DecodeError:
        return jerror("Invalid credentials", code=401)

    log.info("user login successful")
    # Store account role in token to prevent frequent DB lookups
    role = _get_account_role(dec["account_id"]) or "user"
    redirect_to = dec.get("redirect_to", "")

    token = _create_session_token(dec["account_id"], role)
    r = make_response(jsonify(redirect_to=redirect_to), 200)
    set_JWT_cookie(r, token)
    r.cache_control.no_cache = True
    return r


# TODO: add table setup
"""
CREATE TABLE IF NOT EXISTS accounts (
    account_id text PRIMARY KEY,
    role text
);

GRANT SELECT ON TABLE accounts TO amsapi;
GRANT SELECT ON TABLE accounts TO readonly;

CREATE TABLE IF NOT EXISTS session_expunge (
    account_id text PRIMARY KEY,
    threshold timestamp without time zone NOT NULL
);
GRANT SELECT ON TABLE public.session_expunge TO amsapi;
GRANT SELECT ON TABLE public.session_expunge TO readonly;
"""


@metrics.timer("user_logout")
@auth_blueprint.route("/api/v1/user_logout", methods=["POST"])
@cross_origin(origins=origins, supports_credentials=True)
def user_logout() -> Response:
    """Probe Services: direct browser to drop auth cookie
    ---
    responses:
      200:
        description: cookie deletion header
    """
    cookie = (
        "ooni=DELETED; Secure; HttpOnly; SameSite=None; Path=/;"
        " Expires=Thu, 01-Jan-1970 00:00:00 GMT; Max-Age=0;"
    )
    resp = make_response()
    resp.headers.add("Set-Cookie", cookie)
    return resp


def _set_account_role(email_address, role: str) -> int:
    log = current_app.logger
    account_id = hash_email_address(email_address)
    # log.info(f"Giving account {account_id} role {role}")
    # TODO: when role is changed enforce token expunge
    query_params = dict(account_id=account_id, role=role)
    log.info("Creating/Updating account role")
    # 'accounts' is on RocksDB (ACID key-value database)
    query = """INSERT INTO accounts (account_id, role) VALUES"""
    return insert_click(query, [query_params])


@auth_blueprint.route("/api/v1/set_account_role", methods=["POST"])
@role_required("admin")
def set_account_role() -> Response:
    """Set a role to a given account identified by an email address.
    Only for admins.
    ---
    security:
      cookieAuth:
        type: JWT
        in: cookie
        name: ooni
    parameters:
      - in: body
        name: email address and role
        description: data as HTML form or JSON
        required: true
        schema:
          type: object
          properties:
            email_address:
              type: string
            role:
              type: string
    responses:
      200:
        description: Confirmation
    """
    log = current_app.logger
    req = request.json if request.is_json else request.form
    role = req.get("role", "").strip().lower()
    email_address = req.get("email_address", "").strip().lower()
    if EMAIL_RE.fullmatch(email_address) is None:
        return jerror("Invalid email address")
    if role not in ["user", "admin"]:
        return jerror("Invalid role")

    r = _set_account_role(email_address, role)
    log.info(f"Role set {r}")
    return nocachejson()


def _delete_account_data(email_address: str) -> None:
    # Used by integ test
    account_id = hash_email_address(email_address)
    # reset account to "user" role
    # 'accounts' is on RocksDB (ACID key-value database)
    query_params = dict(account_id=account_id, role="user")
    query = """INSERT INTO accounts (account_id, role) VALUES"""
    insert_click(query, [query_params])


def _get_account_role(account_id: str) -> Optional[str]:
    """Get account role from database, or None"""
    query = "SELECT role FROM accounts WHERE account_id = :account_id"
    query_params = dict(account_id=account_id)
    r = query_click_one_row(sql.text(query), query_params)
    return r["role"] if r else None


@auth_blueprint.route("/api/_/account_metadata")
@cross_origin(origins=origins, supports_credentials=True)
def get_account_metadata() -> Response:
    """Get account metadata for logged-in users
    ---
    responses:
      200:
        description: Username and role if logged in.
        schema:
          type: object
    """
    try:
        token = request.cookies.get("ooni", "")
        tok = decode_jwt(token, audience="user_auth")
        return nocachejson(logged_in=True, role=tok["role"])
    except Exception:
        resp = make_response(jsonify(logged_in=False), 401)
        resp.cache_control.no_cache = True
        return resp


@auth_blueprint.route("/api/v1/get_account_role/<email_address>")
@role_required("admin")
def get_account_role(email_address) -> Response:
    """Get account role. Return an error message if the account is not found.
    Only for admins.
    ---
    security:
      cookieAuth:
        type: JWT
        in: cookie
        name: ooni
    parameters:
      - name: email_address
        in: path
        required: true
        type: string
    responses:
      200:
        description: Role or error message
        schema:
          type: object
    """
    log = current_app.logger
    email_address = email_address.strip().lower()
    if EMAIL_RE.fullmatch(email_address) is None:
        return jerror("Invalid email address")
    account_id = hash_email_address(email_address)
    role = _get_account_role(account_id)
    if role is None:
        log.info(f"Getting account {account_id} role: not found")
        return jerror("Account not found")

    log.info(f"Getting account {account_id} role: {role}")
    return nocachejson(role=role)


@auth_blueprint.route("/api/v1/set_session_expunge", methods=["POST"])
@role_required("admin")
def set_session_expunge() -> Response:
    """Force refreshing all session tokens for a given account.
    Only for admins.
    ---
    security:
      cookieAuth:
        type: JWT
        in: cookie
        name: ooni
    parameters:
      - in: body
        name: email address
        description: data as HTML form or JSON
        required: true
        schema:
          type: object
          properties:
            email_address:
              type: string
    responses:
      200:
        description: Confirmation
    """
    log = current_app.logger
    req = request.json if request.is_json else request.form
    email_address = req.get("email_address", "").strip().lower()
    if EMAIL_RE.fullmatch(email_address) is None:
        return jerror("Invalid email address")
    account_id = hash_email_address(email_address)
    log.info(f"Setting expunge for account {account_id}")
    # If an entry is already in place update the threshold as the new
    # value is going to be safer
    # 'session_expunge' is on RocksDB (ACID key-value database)
    log.info("Inserting into Clickhouse session_expunge")
    query = "INSERT INTO session_expunge (account_id) VALUES"
    query_params: Any = dict(account_id=account_id)
    # the `threshold` column defaults to the current time
    insert_click(query, [query_params])
    return nocachejson()


def _remove_from_session_expunge(email_address: str) -> None:
    # Used by integ test
    log = current_app.logger
    account_id = hash_email_address(email_address)
    query_params: Dict[str, Any] = dict(account_id=account_id)
    # 'session_expunge' is on RocksDB (ACID key-value database)
    q1 = "SELECT * FROM session_expunge WHERE account_id = :account_id"
    row = query_click_one_row(sql.text(q1), query_params)
    # https://github.com/ClickHouse/ClickHouse/issues/20546
    if row:
        log.info("Resetting expunge in Clickhouse session_expunge")
        query = "INSERT INTO session_expunge (account_id, threshold) VALUES"
        query_params["threshold"] = 0
        insert_click(query, [query_params])


# TODO: purge session_expunge
