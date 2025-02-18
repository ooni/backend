import logging
from datetime import datetime, timezone, timedelta
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response

from ...common.dependencies import get_settings
from ...common.routers import BaseModel
from ...common.auth import create_jwt, decode_jwt, jwt
from ...common.config import Settings
from ...common.utils import setnocacheresponse

router = APIRouter(prefix="/v1")

log = logging.getLogger(__name__)


class ProbeLogin(BaseModel):
    # Allow None username and password
    # to deliver informational 401 error when they're missing
    username: str | None = None
    # not actually used but necessary to be compliant with the old API schema
    password: str | None = None


class ProbeLoginResponse(BaseModel):
    token: str
    expire: str


@router.post("/login", tags=["ooniprobe"], response_model=ProbeLoginResponse)
def probe_login_post(
    probe_login: ProbeLogin,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> ProbeLoginResponse:

    if probe_login.username is None or probe_login.password is None:
        raise HTTPException(status_code=401, detail="Missing credentials")

    token = probe_login.username
    # TODO: We have to find a way to explicitly log metrics with prometheus.
    # We're currently using the instrumentator default metrics, like http response counts
    # Maybe using the same exporter as the instrumentator?
    try:
        dec = decode_jwt(token, audience="probe_login", key=settings.jwt_encryption_key)
        registration_time = dec["iat"]
        log.info("probe login: successful")
        # metrics.incr("probe_login_successful")
    except jwt.exceptions.MissingRequiredClaimError:
        log.info("probe login: invalid or missing claim")
        # metrics.incr("probe_login_failed")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    except jwt.exceptions.InvalidSignatureError:
        log.info("probe login: invalid signature")
        # metrics.incr("probe_login_failed")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    except jwt.exceptions.DecodeError:
        # Not a JWT token: treat it as a "legacy" login
        # return jerror("Invalid or missing credentials", code=401)
        log.info("probe login: legacy login successful")
        # metrics.incr("probe_legacy_login_successful")
        registration_time = None

    exp = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {"registration_time": registration_time, "aud": "probe_token"}
    token = create_jwt(payload, key=settings.jwt_encryption_key)
    # expiration string used by the probe e.g. 2006-01-02T15:04:05Z
    expire = exp.strftime("%Y-%m-%dT%H:%M:%SZ")
    login_response = ProbeLoginResponse(token=token, expire=expire)
    setnocacheresponse(response)

    return login_response


class ProbeRegister(BaseModel):
    # None of this values is actually used, but I add them
    # to keep it compliant with the old api
    password: str
    platform: str
    probe_asn: str
    probe_cc: str
    software_name: str
    software_version: str
    supported_tests: List[str]


class ProbeRegisterResponse(BaseModel):
    client_id: str


@router.post("/register", tags=["ooniprobe"], response_model=ProbeRegisterResponse)
def probe_register_post(
    probe_register: ProbeRegister,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> ProbeRegisterResponse:
    """Probe Services: Register

    Probes send a random string called password and receive a client_id

    The client_id/password tuple is saved by the probe and long-lived

    Note that most of the request body arguments are not actually
    used but are kept here to use the same API as the old version
    
    """

    # **IMPORTANT** You have to compute this token using a different key
    # to the one used in ooniauth service, because you could allow
    # a login bypass attack if you don't. 
    #
    # Note that this token is generated regardless of any authentication, 
    # so if you use the same jwt_encryption_key for ooniauth, you give users
    # an auth token for free
    #
    # We set this up in the terraform level

    # client_id is a JWT token with "issued at" claim and
    # "audience" claim. The "issued at" claim is rounded up.
    issued_at = int(time.time())
    payload = {"iat": issued_at, "aud": "probe_login"}
    client_id = create_jwt(payload, key=settings.jwt_encryption_key)
    log.info("register successful")

    register_response = ProbeRegisterResponse(client_id=client_id)
    setnocacheresponse(response)

    return register_response


class ProbeUpdate(BaseModel):
    """
    The original format of this comes from: 
    https://github.com/ooni/orchestra/blob/master/registry/registry/handler/registry.go#L25
    """
    probe_cc : Optional[str] = None
    probe_asn : Optional[str] = None
    platform : Optional[str]  = None

    software_name : Optional[str]  = None
    software_version : Optional[str]  = None
    supported_tests : Optional[List[str]] = None

    network_type : Optional[str] = None
    available_bandwidth : Optional[str] = None
    language : Optional[str] = None

    token : Optional[str] = None

    probe_family : Optional[str] = None
    probe_id : Optional[str] = None

    password : Optional[str] = None


class ProbeUpdateResponse(BaseModel):
    status: str


@router.put("/update/{client_id}", tags=["ooniprobe"])
def probe_update_post(probe_update: ProbeUpdate) -> ProbeUpdateResponse:
    log.info("update successful")
    return ProbeUpdateResponse(status="ok")
