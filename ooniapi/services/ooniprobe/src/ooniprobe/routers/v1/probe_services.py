import logging
from datetime import datetime, timezone, timedelta
import time
from typing import List, Any, Dict, Tuple, Optional
import random
import zstd
from hashlib import sha512
import asyncio
import io

import geoip2
import geoip2.errors
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status, Header
from pydantic import Field
from ooniauth_py import ProtocolError, CredentialError, DeserializationFailed
import httpx

from ...utils import (
    generate_report_id,
    extract_probe_ipaddr,
    lookup_probe_cc,
    lookup_probe_network,
    error,
    compare_probe_msmt_cc_asn
)

from ...dependencies import CCReaderDep, ASNReaderDep, ClickhouseDep, SettingsDep, LatestManifestDep, PostgresSessionDep, S3ClientDep
from ..reports import Metrics
from ...common.dependencies import get_settings
from ...common.routers import BaseModel
from ...common.auth import create_jwt, decode_jwt, jwt
from ...common.config import Settings
from ...common.utils import setnocacheresponse
from ...models import OONIProbeManifest, OONIProbeServerState
from ...prio import generate_test_list

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
    run_type: str = "timed"
    charging: bool = True
    probe_cc: str = "ZZ"
    probe_asn: str = "AS0"
    on_wifi: bool = False
    charging: bool = False
    software_name: str = ""
    software_version: str = ""
    web_connectivity: Optional[Dict[str, Any]] = None


class CheckInResponse(BaseModel):
    """
    v:
      type: integer
      description: response format version
    probe_cc:
      type: string
      description: probe CC inferred from GeoIP or ZZ
    probe_asn:
      type: string
      description: probe ASN inferred from GeoIP or AS0
    probe_network_name:
      type: string
      description: probe network name inferred from GeoIP or None
    utc_time:
      type: string
      description: current UTC time as YYYY-mm-ddTHH:MM:SSZ
    conf:
      type: object
      description: auxiliary configuration parameters
      features:
        type: object
        description: feature flags
    tests:
      type: object
      description: test-specific configuration
      properties:
        web_connectivity:
          type: object
          properties:
            report_id:
              type: string
            urls:
              type: array
              items:
                type: object
                properties:
                  category_code:
                    type: string
                  country_code:
                    type: string
                  url:
                    type: string
    """

    v: int
    probe_cc: str
    probe_asn: str
    probe_network_name: Optional[str]
    utc_time: str
    conf: Dict[str, Any]
    tests: Dict[str, Any]


class TestHelperEntry(BaseModel):
    address: str
    type: str
    front: Optional[str] = None


class ListTestHelpersResponse(BaseModel):
    dns: List[TestHelperEntry]
    http_return_json_headers: List[TestHelperEntry] = Field(
        alias="http-return-json-headers"
    )
    ssl: List[TestHelperEntry]
    tcp_echo: List[TestHelperEntry] = Field(alias="tcp-echo")
    traceroute: List[TestHelperEntry]
    web_connectivity: List[TestHelperEntry] = Field(alias="web-connectivity")


@router.get("/test-helpers", tags=["ooniprobe"])
def list_test_helpers(response: Response):
    setnocacheresponse(response)
    conf = generate_test_helpers_conf()
    conf_typed = {}
    for key, value in conf.items():
        conf_typed[key] = [TestHelperEntry(**e) for e in value]

    return ListTestHelpersResponse.model_validate(conf_typed)


@router.post("/check-in", tags=["ooniprobe"])
def check_in(
    request: Request,
    response: Response,
    check_in: CheckIn,
    cc_reader: CCReaderDep,
    asn_reader: ASNReaderDep,
    clickhouse: ClickhouseDep,
    settings: SettingsDep,
) -> CheckInResponse:

    # TODO: Implement throttling
    run_type = check_in.run_type
    charging = check_in.charging
    probe_cc = check_in.probe_cc.upper()
    probe_asn = check_in.probe_asn
    software_name = check_in.software_name
    software_version = check_in.software_version

    resp, probe_cc, asn_i = probe_geoip(
        request,
        probe_cc,
        probe_asn,
        cc_reader,
        asn_reader,
    )

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
            clickhouse, probe_cc, category_codes, asn_i, url_limit, False
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
            "openvpn_enabled": False,
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
    resp["utc_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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
        rid = generate_report_id(tn, settings, probe_cc, asn_i)
        resp["tests"].setdefault(tn, {})  # type: ignore
        resp["tests"][tn]["report_id"] = rid  # type: ignore

    til = len(test_items)
    log.debug(
        f"check-in params: {url_limit} {til} '{probe_cc}' '{charging}' '{run_type}' '{software_name}' '{software_version}'"
    )

    setnocacheresponse(response)
    checkin_response = CheckInResponse(
        v=resp["v"],
        probe_cc=resp["probe_cc"],
        probe_asn=resp["probe_asn"],
        probe_network_name=resp["probe_network_name"],
        utc_time=resp["utc_time"],
        conf=resp["conf"],
        tests=resp["tests"],
    )

    return checkin_response


def probe_geoip(
    request: Request,
    probe_cc: str,
    asn: str,
    cc_reader: CCReaderDep,
    asn_reader: ASNReaderDep,
) -> Tuple[Dict, str, int]:
    """Looks up probe CC, ASN, network name using GeoIP, prepare
    response dict
    """
    db_probe_cc = "ZZ"
    db_asn = "AS0"
    db_probe_network_name = None
    try:
        ipaddr = extract_probe_ipaddr(request)
        db_probe_cc = lookup_probe_cc(ipaddr, cc_reader)
        db_asn, db_probe_network_name = lookup_probe_network(ipaddr, asn_reader)
        Metrics.GEOIP_ADDR_FOUND.labels(probe_cc=db_probe_cc, asn=db_asn).inc()
    except geoip2.errors.AddressNotFoundError:
        Metrics.GEOIP_ADDR_NOT_FOUND.inc()
    except Exception as e:
        log.error(str(e), exc_info=True)

    if probe_cc != "ZZ" and probe_cc != db_probe_cc:
        log.info(f"probe_cc != db_probe_cc ({probe_cc} != {db_probe_cc})")
        Metrics.GEOIP_CC_DIFFERS.inc()
    if asn != "AS0" and asn != db_asn:
        log.info(f"probe_asn != db_probe_as ({asn} != {db_asn})")
        Metrics.GEOIP_ASN_DIFFERS.inc()

    # We always returns the looked up probe_cc and probe_asn to the probe
    resp: Dict[str, Any] = dict(v=1)
    resp["probe_cc"] = db_probe_cc
    resp["probe_asn"] = db_asn
    resp["probe_network_name"] = db_probe_network_name

    # Don't override probe_cc or asn unless the probe has omitted these
    # values. This is done because the IP address we see might not match the
    # actual probe ipaddr in cases in which a circumvention tool is being used.
    # TODO: eventually we should have the probe signal to the backend that it
    # wants the lookup to be done by the backend and have it pass the public IP
    # through a specific header.
    if probe_cc == "ZZ" and asn == "AS0":
        probe_cc = db_probe_cc
        asn = db_asn

    assert asn.startswith("AS")
    asn_int = int(asn[2:])
    assert probe_cc.isalpha()
    assert len(probe_cc) == 2

    return resp, probe_cc, asn_int


def generate_test_helpers_conf() -> Dict:
    # Load-balance test helpers deterministically
    conf = {
        "dns": [
            {"address": "37.218.241.93:57004", "type": "legacy"},
            {"address": "37.218.241.93:57004", "type": "legacy"},
        ],
        "http-return-json-headers": [
            {"address": "http://37.218.241.94:80", "type": "legacy"},
            {"address": "http://37.218.241.94:80", "type": "legacy"},
        ],
        "ssl": [
            {"address": "https://37.218.241.93", "type": "legacy"},
            {"address": "https://37.218.241.93", "type": "legacy"},
        ],
        "tcp-echo": [
            {"address": "37.218.241.93", "type": "legacy"},
            {"address": "37.218.241.93", "type": "legacy"},
        ],
        "traceroute": [
            {"address": "37.218.241.93", "type": "legacy"},
            {"address": "37.218.241.93", "type": "legacy"},
        ],
        "web-connectivity": [
            {"address": "httpo://o7mcp5y4ibyjkcgs.onion", "type": "legacy"},
            {"address": "https://wcth.ooni.io", "type": "https"},
            {
                "address": "https://d33d1gs9kpq1c5.cloudfront.net",
                "front": "d33d1gs9kpq1c5.cloudfront.net",
                "type": "cloudfront",
            },
            {"address": "httpo://y3zq5fwelrzkkv3s.onion", "type": "legacy"},
            {"address": "https://wcth.ooni.io", "type": "https"},
            {
                "address": "https://d33d1gs9kpq1c5.cloudfront.net",
                "front": "d33d1gs9kpq1c5.cloudfront.net",
                "type": "cloudfront",
            },
        ],
    }
    conf["web-connectivity"] = random_web_test_helpers(
        [
            "https://6.th.ooni.org",
            "https://5.th.ooni.org",
        ]
    )
    conf["web-connectivity"].append(
        {
            "address": "https://d33d1gs9kpq1c5.cloudfront.net",
            "front": "d33d1gs9kpq1c5.cloudfront.net",
            "type": "cloudfront",
        }
    )
    return conf


def random_web_test_helpers(th_list: List[str]) -> List[Dict]:
    """Randomly sort test helpers"""
    random.shuffle(th_list)
    out = []
    for th_addr in th_list:
        out.append({"address": th_addr, "type": "https"})
    return out

# -- <Anonymous Credentials> ------------------------------------

class ManifestResponse(BaseModel):
    nym_scope: str
    public_parameters: str
    submission_policy: Dict[str, Any]
    version: str

@router.get("/manifest", tags=["anonymous_credentials"])
def manifest(manifest : LatestManifestDep) -> ManifestResponse:
    return ManifestResponse(
        nym_scope="ooni.org/{probe_cc}/{probe_asn}",
        public_parameters=manifest.server_state.public_parameters,
        submission_policy={},
        version=manifest.version
        )

class RegisterRequest(BaseModel):
    manifest_version: str
    credential_sign_request: str

class RegisterResponse(BaseModel):
    credential_sign_response: str
    emission_day: int

# TODO: choose a better name for this endpoint
@router.post("/sign_credential", tags=["anonymous_credentials"])
def sign_credential(register_request: RegisterRequest, session : PostgresSessionDep):

    manifest = OONIProbeManifest.get_by_version(session, register_request.manifest_version)
    if manifest is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            {
                "error" : "manifest_not_found",
                "message" : f"No manifest with version '{register_request.manifest_version}' was found"}
            )
    state: OONIProbeServerState = manifest.server_state
    protocol_state = state.to_protocol()

    try:
        resp = protocol_state.handle_registration_request(register_request.credential_sign_request)
    except (ProtocolError, CredentialError, DeserializationFailed) as e:
        raise to_http_exception(e)

    return RegisterResponse(
        credential_sign_response=resp,
        emission_day=protocol_state.today()
    )


def to_http_exception(error: ProtocolError | CredentialError | DeserializationFailed):

    error_to_string = {
        ProtocolError : "protocol_error",
        DeserializationFailed : "deserialization_failed",
        CredentialError : "credential_error"
    }

    error_str = error_to_string[type(error)]

    if isinstance(error, DeserializationFailed):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": error_str, "detail": str(error)}
        )
    if isinstance(error, (CredentialError, ProtocolError)): #
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": error_str, "message": str(error)}
        )

class SubmitMeasurementResponse(BaseModel):
    """
    Acknowledge
    """

    measurement_uid: str | None = Field(
        examples=["20210208220710.181572_MA_ndt_7888edc7748936bf"], default=None
    )

class SubmitMeasurementRequest(BaseModel):

    format: str
    content: Dict[str, Any]
    # not post quantum, in the future we might want to use a hashed key for storage
    nym: str
    zkp_request: str
    age_range: Tuple[int,int]
    msm_range: Tuple[int,int]

@router.post("/submit_measurement/{report_id}")
async def submit_measurement(
    report_id: str,
    submit_request: SubmitMeasurementRequest,
    response: Response,
    cc_reader: CCReaderDep,
    asn_reader: ASNReaderDep,
    settings: SettingsDep,
    s3_client: S3ClientDep,
    content_encoding: str = Header(default=None),
) -> SubmitMeasurementResponse | Dict[str, Any]:
    """
    Submit measurement
    """
    setnocacheresponse(response)
    empty_measurement = {}
    try:
        rid_timestamp, test_name, cc, asn, format_cid, rand = report_id.split("_")
    except Exception:
        log.info("Unexpected report_id %r", report_id[:200])
        raise error("Incorrect format")

    # TODO validate the timestamp?
    good = len(cc) == 2 and test_name.isalnum() and 1 < len(test_name) < 30
    if not good:
        log.info("Unexpected report_id %r", report_id[:200])
        error("Incorrect format")

    try:
        asn_i = int(asn)
    except ValueError:
        log.info("ASN value not parsable %r", asn)
        error("Incorrect format")

    if asn_i == 0:
        log.info("Discarding ASN == 0")
        Metrics.MSMNT_DISCARD_ASN0.inc()
        return empty_measurement

    if cc.upper() == "ZZ":
        log.info("Discarding CC == ZZ")
        Metrics.MSMNT_DISCARD_CC_ZZ.inc()
        return empty_measurement


    # TODO
    # Parse data into a json
    # verify with anonymous credentials parameters
    # add additional information to the json
    # convert to data again

    # Write the whole body of the measurement in a directory based on a 1-hour
    # time window
    now = datetime.now(timezone.utc)
    h = sha512(data).hexdigest()[:16]
    ts = now.strftime("%Y%m%d%H%M%S.%f")

    # msmt_uid is a unique id based on upload time, cc, testname and hash
    msmt_uid = f"{ts}_{cc}_{test_name}_{h}"
    Metrics.MSMNT_RECEIVED_CNT.inc()

    compare_probe_msmt_cc_asn(cc, asn, request, cc_reader, asn_reader)
    # Use exponential back off with jitter between retries
    N_RETRIES = 3
    for t in range(N_RETRIES):
        try:
            url = f"{settings.fastpath_url}/{msmt_uid}"

            async with httpx.AsyncClient() as client:
                resp = await client.post(url, content=data, timeout=59)

            assert resp.status_code == 200, resp.content
            return SubmitMeasurementResponse(measurement_uid=msmt_uid)

        except Exception as exc:
            log.error(
                f"[Try {t+1}/{N_RETRIES}] Error trying to send measurement to the fastpath. Error: {exc}"
            )
            sleep_time = random.uniform(0, min(3, 0.3 * 2 ** t))
            await asyncio.sleep(sleep_time)

    Metrics.SEND_FASTPATH_FAILURE.inc()

    # wasn't possible to send msmnt to fastpath, try to send it to s3
    try:
        s3_client.upload_fileobj(
            io.BytesIO(data), Bucket=settings.failed_reports_bucket, Key=report_id
        )
    except Exception as exc:
        log.error(f"Unable to upload measurement to s3. Error: {exc}")
        Metrics.SEND_S3_FAILURE.inc()

    log.error(f"Unable to send report to fastpath. report_id: {report_id}")
    Metrics.MISSED_MSMNTS.inc()
    return empty_measurement
