import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response

from ...common.dependencies import get_settings
from ...common.routers import BaseModel
from ...common.auth import create_jwt, decode_jwt, jwt
from ...common.config import Settings
from ...common.utils import setnocacheresponse

router = APIRouter(prefix="/v1")

log = logging.getLogger(__name__)

class ProbeLogin(BaseModel):
    username : str 
    # not actually used but necessary to be compliant with the old API schema
    password : str   

class ProbeLoginResponse(BaseModel):
    token : str
    expire : str

@router.get("/ooniprobe/login/", tags=["ooniprobe"], response_model=ProbeLoginResponse)
def probe_login_post(
    probe_login : ProbeLogin, 
    response : Response,
    settings : Settings = Depends(get_settings),
) -> ProbeLoginResponse:
    global log

    token = probe_login.username
    try:
        dec = decode_jwt(token, audience="probe_login", key=settings.jwt_encryption_key)
        registration_time = dec["iat"]
        log.info("probe login successful")
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
        log.info("probe legacy login successful")
        # metrics.incr("probe_legacy_login_successful")
        registration_time = None

    exp = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {"registration_time": registration_time, "aud": "probe_token"}
    token = create_jwt(payload, key=settings.jwt_encryption_key)
    # expiration string used by the probe e.g. 2006-01-02T15:04:05Z
    expire = exp.strftime("%Y-%m-%dT%H:%M:%SZ")
    login_response = ProbeLoginResponse(token=token, expire = expire)
    setnocacheresponse(response)

    return login_response

