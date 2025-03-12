import logging
from datetime import datetime, timezone, timedelta
import time
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Response
from prometheus_client import Counter, Info, Gauge
from enum import Enum

from ...common.dependencies import get_settings
from ...common.routers import BaseModel
from ...common.auth import create_jwt, decode_jwt, jwt
from ...common.config import Settings
from ...common.utils import setnocacheresponse

router = APIRouter(prefix="/v1")

log = logging.getLogger(__name__)


class Metrics:
    PROBE_LOGIN = Counter(
        "probe_login_requests",
        "Requests made to the probe login endpoint",
        labelnames=["state", "detail", "login"],
    )

    PROBE_UPDATE_INFO = Info(
        "probe_update_info",
        "Information reported in the probe update endpoint",
    )

    CHECK_IN_TEST_LIST_COUNT = Gauge("check-in-test-list-count", "Amount of test lists present in each experiment")

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

    try:
        dec = decode_jwt(token, audience="probe_login", key=settings.jwt_encryption_key)
        registration_time = dec["iat"]

        log.info("probe login: successful")
        Metrics.PROBE_LOGIN.labels(
            login="standard", detail="ok", state="successful"
        ).inc()

    except jwt.exceptions.MissingRequiredClaimError:
        log.info("probe login: invalid or missing claim")
        Metrics.PROBE_LOGIN.labels(
            login="standard", detail="invalid_or_missing_claim", state="failed"
        ).inc()

        raise HTTPException(status_code=401, detail="Invalid credentials")
    except jwt.exceptions.InvalidSignatureError:
        log.info("probe login: invalid signature")
        Metrics.PROBE_LOGIN.labels(
            login="standard", detail="invalid_signature", state="failed"
        ).inc()

        raise HTTPException(status_code=401, detail="Invalid credentials")
    except jwt.exceptions.DecodeError:
        log.info("probe login: legacy login successful")
        Metrics.PROBE_LOGIN.labels(
            login="legacy", detail="ok", state="successful"
        ).inc()

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

    probe_cc: Optional[str] = None
    probe_asn: Optional[str] = None
    platform: Optional[str] = None

    software_name: Optional[str] = None
    software_version: Optional[str] = None
    supported_tests: Optional[List[str]] = None

    network_type: Optional[str] = None
    available_bandwidth: Optional[str] = None
    language: Optional[str] = None

    token: Optional[str] = None

    probe_family: Optional[str] = None
    probe_id: Optional[str] = None

    password: Optional[str] = None


class ProbeUpdateResponse(BaseModel):
    status: str


@router.put("/update/{client_id}", tags=["ooniprobe"])
def probe_update_post(probe_update: ProbeUpdate) -> ProbeUpdateResponse:
    log.info("update successful")

    # Log update metadata into prometheus
    probe_update_dict = probe_update.model_dump(exclude_none=True)

    # Info doesn't allows list, if we have a list we have to convert it
    # to string
    if probe_update_dict.get("supported_tests") is not None:
        tests = probe_update_dict["supported_tests"]
        tests.sort()
        tests_str = ";".join(tests)
        probe_update_dict["supported_tests"] = tests_str

    Metrics.PROBE_UPDATE_INFO.info(probe_update_dict)

    return ProbeUpdateResponse(status="ok")

class CheckIn(BaseModel):
    run_type: str = 'timed'
    charging: bool = True
    probe_cc: str = "ZZ"
    probe_asn: str = "AS0"
    software_name: str = ""
    software_version: str = ""
    web_connectivity: Optional[Dict[str, Any]] = None

class CheckInResponse(BaseModel):
    pass

@router.post("/check-in", tags=["ooniprobe"])
def check_in(check_in : CheckIn) -> CheckInResponse:

    # TODO: Implement throttling
    run_type = check_in.run_type
    charging = check_in.charging
    probe_cc = check_in.probe_cc.upper()
    probe_asn = check_in.probe_asn
    software_name = check_in.software_name
    software_version = check_in.software_version

    resp, probe_cc, asn_i = probe_geoip(probe_cc, probe_asn)

    # On run_type=manual preserve the old behavior: test the whole list
    # On timed runs test few URLs, especially when on battery
    if run_type == "manual":
        url_limit = 9999  # same as prio.py
    elif charging:
        url_limit = 100
    else:
        url_limit = 20

    try:
        charging = bool(charging)
    except Exception:
        log.error(
            f"check-in params: {url_limit} '{probe_cc}' '{charging}' '{run_type}' '{software_name}' '{software_version}'"
        )

    if check_in.web_connectivity is not None:
        catcodes = check_in.web_connectivity.get("category_codes", [])
        if isinstance(catcodes, str):
            category_codes = catcodes.split(",")
        else:
            category_codes = catcodes

    else:
        category_codes = []

    for c in category_codes:
        assert c.isalpha()

    try:
        test_items, _1, _2 = generate_test_list(
            probe_cc, category_codes, asn_i, url_limit, False
        )
    except Exception as e:
        log.error(e, exc_info=True)
        # TODO: use same failover as prio.py:list_test_urls
        # failover_generate_test_list runs without any database interaction
        # test_items = failover_generate_test_list(country_code, category_codes, limit)
        test_items = []

    Metrics.CHECK_IN_TEST_LIST_COUNT.set(len(test_items))

    conf: Dict[str, Any] = dict(
        features={
            # TODO(https://github.com/ooni/probe-cli/pull/1522): we disable torsf until we have
            # addressed the issue with the fast.ly based rendezvous method being broken
            "torsf_enabled": False,
            "vanilla_tor_enabled": True,
        }
    )

    # set webconnectivity_0.5 feature flag for some probes
    # Temporarily disabled while we work towards deploying this in prod:
    # https://github.com/ooni/probe/issues/2674
    #
    # octect = extract_probe_ipaddr_octect(1, 0)
    # if octect in (34, 239):
    #    conf["features"]["webconnectivity_0.5"] = True

    conf["test_helpers"] = generate_test_helpers_conf()

    resp["tests"] = {
        "web_connectivity": {"urls": test_items},
    }
    resp["conf"] = conf
    resp["utc_time"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    test_names = (
        "bridge_reachability",
        "dash",
        "dns_consistency",
        "dnscheck",
        "facebook_messenger",
        "http_header_field_manipulation",
        "http_host",
        "http_invalid_request_line",
        "http_requests",
        "meek_fronted_requests_test",
        "multi_protocol_traceroute",
        "ndt",
        "psiphon",
        "riseupvpn",
        "tcp_connect",
        "telegram",
        "tor",
        "urlgetter",
        "vanilla_tor",
        "web_connectivity",
        "whatsapp",
    )
    for tn in test_names:
        rid = generate_report_id(tn, probe_cc, asn_i)
        resp["tests"].setdefault(tn, {})  # type: ignore
        resp["tests"][tn]["report_id"] = rid  # type: ignore

    til = len(test_items)
    log.debug(
        f"check-in params: {url_limit} {til} '{probe_cc}' '{charging}' '{run_type}' '{software_name}' '{software_version}'"
    )

    # TODO(luis) use this to set the response to use no cache 
    # setnocacheresponse(response)

    return nocachejson(**resp)
    
    return CheckInResponse()