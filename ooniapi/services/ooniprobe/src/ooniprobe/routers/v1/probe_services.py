import asyncio
import io
import logging
from datetime import datetime, timezone, timedelta
import time
from enum import Enum
from datetime import datetime, timedelta, timezone
from hashlib import sha512
from typing import (
    List,
    Any,
    Dict,
    Tuple,
    Optional,
    Annotated,
)
import random

from pydantic import Field, IPvAnyAddress
import ooniauth_py
import ujson
from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from ooniauth_py import (
    ProtocolError,
    CredentialError,
    DeserializationFailed,
    ServerState,
)
from starlette.concurrency import run_in_threadpool
import ujson

from ...common.auth import create_jwt, decode_jwt, jwt
from ...common.dependencies import ClickhouseDep
from ...common.errors import AddressNotFoundError
from ...common.prio import (
    FailoverTestListDep,
    failover_generate_test_list,
    generate_test_list,
)
from ...common.routers import BaseModel
from ...common.utils import setcacheresponse, setnocacheresponse
from ...dependencies import (
    ASNCCReaderDep,
    ManifestDep,
    ManifestResponse,
    PolicyEntry,
    PostgresSessionDep,
    SettingsDep,
    TorTargetsDep,
    PsiphonConfigDep
)
from ...utils import (
    error,
    extract_probe_ipaddr,
    generate_report_id,
    get_cc_asn,
    normalize_asn,
    register_geoip_anomaly,
    compare_probe_msmt_cc_asn,
    geolookup_probe,
)

from ..reports import Metrics

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
    settings: SettingsDep,
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
    settings: SettingsDep,
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
    asn_cc_reader: ASNCCReaderDep,
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
    ipaddr = extract_probe_ipaddr(request)
    resp, probe_cc, asn_i = probe_geoip(
        ipaddr,
        probe_cc,
        probe_asn,
        asn_cc_reader,
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
            "vanilla_tor_enabled": False,
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
    ipaddr: str,
    probe_cc: str,
    asn: str,
    asn_cc_reader: ASNCCReaderDep,
) -> Tuple[Dict, str, int]:
    """Looks up probe CC, ASN, network name using GeoIP, prepare
    response dict
    """
    db_probe_cc = "ZZ"
    db_asn = "AS0"
    db_probe_network_name = None
    try:
        db_probe_cc, db_asn, db_probe_network_name  = geolookup_probe(ipaddr, asn_cc_reader)
        Metrics.GEOIP_ADDR_FOUND.labels(probe_cc=db_probe_cc, asn=db_asn).inc()
    except AddressNotFoundError:
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


class TestListUrlsMeta(BaseModel):
    count: int
    current_page: int
    limit: int
    next_url: str
    pages: int


class TestListUrlsResult(BaseModel):
    category_code: str
    country_code: str
    url: str


class TestListUrlsResponse(BaseModel):
    """
    URL test list
    """

    metadata: TestListUrlsMeta
    results: List[TestListUrlsResult]


@router.get("/test-list/urls")
def list_test_urls(
    clickhouse: ClickhouseDep,
    failover_test_items: FailoverTestListDep,
    response: Response,
    category_codes: Annotated[
        str | None,
        Query(
            description="Comma separated list of URL categories, all uppercase",
            pattern=r"[A-Z,]*",
        ),
    ] = None,
    country_code: Annotated[
        str,
        Query(
            description="Two letter, uppercase country code",
            min_length=2,
            max_length=2,
            alias="probe_cc",
        ),
    ] = "ZZ",
    limit: Annotated[
        int, Query(description="Maximum number of URLs to return", le=9999)
    ] = -1,
    debug: Annotated[
        bool,
        Query(
            description="Include measurement counts and priority",
        ),
    ] = False,
) -> TestListUrlsResponse | Dict[str, Any]:
    """
    Generate test URL list with prioritization
    """
    try:
        country_code = country_code.upper()
        category_codes_list = category_codes.split(",") if category_codes else None
        if limit == -1:
            limit = 9999
    except Exception as e:
        log.error(e, exc_info=True)
        setnocacheresponse(response)
        return {}

    try:
        test_items, _1, _2 = generate_test_list(
            clickhouse, country_code, category_codes_list, 0, limit, debug
        )
    except Exception as e:
        log.error(e, exc_info=True)
        # failover_generate_test_list runs without any database interaction
        test_items = failover_generate_test_list(
            failover_test_items, category_codes_list, limit
        )

    # TODO: remove current_page / next_url / pages ?
    Metrics.TEST_LIST_URLS_COUNT.set(len(test_items))
    out = TestListUrlsResponse(
        metadata=TestListUrlsMeta(
            count=len(test_items), current_page=-1, limit=-1, next_url="", pages=1
        ),
        results=[TestListUrlsResult(**item) for item in test_items],
    )
    setcacheresponse("1s", response)
    return out


class GeoLookupResult(BaseModel):
    cc: Optional[str] = Field(default=None, description="Country Code")
    asn: Optional[int] = Field(default=None, description="Autonomous System Number (ASN)")
    as_name: Optional[str] = Field(default=None, description="Autonomous System Name")


class GeoLookupRequest(BaseModel):
    addresses: List[IPvAnyAddress] = Field(
        description="list of IPv4 or IPv6 address to geolookup"
    )


class GeoLookupResponse(BaseModel):
    v: int = Field(description="response format version", default=1)
    geolocation: Dict[IPvAnyAddress, GeoLookupResult] = Field(
        description="Dict of IP addresses to GeoLookupResult"
    )


@router.post("/geolookup", tags=["ooniprobe"])
async def geolookup(
    data: GeoLookupRequest,
    response: Response,
    asn_cc_reader: ASNCCReaderDep,
) -> GeoLookupResponse:
    geolocation = dict()

    # for each address provided, call probe_geoip and add the data to our response
    for ipaddr in data.addresses:
        try:
            cc, asn, as_name = geolookup_probe(ipaddr, asn_cc_reader)
            if asn is not None and asn.startswith("AS"):
                asn = int(asn[2:])

        except AddressNotFoundError:
            cc = None
            asn = as_name = None
        geolocation[ipaddr] = GeoLookupResult(
            cc=cc, asn=asn, as_name=as_name
        )

    setnocacheresponse(response)
    return GeoLookupResponse(geolocation=geolocation)


class CollectorEntry(BaseModel):
    # not actually used but necessary to be compliant with the old API schema
    address: str = Field(description="Address of collector")
    front: Optional[str] = Field(default=None, description="Fronted domain")
    type: Optional[str] = Field(default=None, description="Type of collector")


@router.get(
    "/collectors",
    response_model_exclude_none=True,
    response_model=List[CollectorEntry],
    tags=["ooniprobe"],
)
def list_collectors(
    settings: SettingsDep,
):
    config_collectors = settings.collectors
    collectors_response = []
    for entry in config_collectors:
        collector = CollectorEntry(**entry)
        collectors_response.append(collector)
    return collectors_response


# -- <Anonymous Credentials> ------------------------------------


@router.get("/manifest", tags=["anonymous_credentials"])
def manifest(manifest: ManifestDep, response: Response) -> ManifestResponse:
    # Cache for 1 minute
    setcacheresponse("1m", response)
    return manifest


class RegisterRequest(BaseModel):
    manifest_version: str
    credential_sign_request: str


class RegisterResponse(BaseModel):
    credential_sign_response: str
    emission_day: int


# TODO: choose a better name for this endpoint
@router.post("/sign_credential", tags=["anonymous_credentials"])
def sign_credential(
    register_request: RegisterRequest, manifest: ManifestDep, settings: SettingsDep
) -> RegisterResponse:
    if register_request.manifest_version != manifest.meta.version:
        _raise_manifest_not_found(register_request.manifest_version)

    protocol_state = ServerState.from_creds(
        manifest.manifest.public_parameters, settings.anonc_secret_key
    )

    try:
        resp = protocol_state.handle_registration_request(
            register_request.credential_sign_request
        )
    except (ProtocolError, CredentialError, DeserializationFailed) as e:
        raise to_http_exception(e)

    return RegisterResponse(
        credential_sign_response=resp, emission_day=protocol_state.today()
    )


def _anonc_exc_to_str(error: ProtocolError | CredentialError | DeserializationFailed) -> str:
    """
    returns a short error string depending on the error type
    """
    type_to_str = {
        ProtocolError: "protocol_error",
        DeserializationFailed: "deserialization_failed",
        CredentialError: "credential_error",
    }
    return type_to_str[type(error)]


def to_http_exception(error: ProtocolError | CredentialError | DeserializationFailed):
    type_str = _anonc_exc_to_str(error)

    assert isinstance(error, (ProtocolError, CredentialError, DeserializationFailed))
    status_code = (
        status.HTTP_400_BAD_REQUEST
        if isinstance(error, DeserializationFailed)
        else status.HTTP_403_FORBIDDEN
    )

    return HTTPException(
        status_code=status_code, detail={"error": type_str, "message": str(error)}
    )


class SubmitMeasurementRequest(BaseModel):
    format: str
    content: Dict[str, Any]
    # -- < Anonymous Credentials > ----------------------
    # not post quantum, in the future we might want to use a hashed key for storage
    nym: str | None = None
    zkp_request: str | None = Field(description=
        "zkp request computed by the ooniauth-core library, base-64 encoded as a string. "
        "Note that this has to be computed with the ASN in the same format as the `probe_asn` in "
        "the measurement body (`content` key)",
        default = None
    )
    manifest_version: str | None = None
    protocol_version: str | None = Field(description =
        "`ooniauth-core` version used by the **probe** sending this request",
        default = None
        )


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNVERIFIED = "unverified"

    @property
    def code(self) -> str:
        return {
            VerificationStatus.VERIFIED: "t",
            VerificationStatus.FAILED: "f",
            VerificationStatus.UNVERIFIED: "u",
        }[self]


class SubmitMeasurementResponse(BaseModel):
    """
    Acknowledge
    """

    measurement_uid: str | None = Field(
        examples=["20210208220710.181572_MA_ndt_7888edc7748936bf"], default=None
    )
    verification_status: VerificationStatus = Field(
        description="Verification status: verified, failed, or unverified"
    )
    submit_response: str | None = Field(
        description="Anonymous credential verification response. Null if verification failed"
    )
    protocol_version: str = Field(
        description="Protocol version used by the backend: current `ooniauth-core` version",
        default=ooniauth_py.get_protocol_version(),
    )
    error: str | None = Field(
        description="If there was an error accepting this measurement. Note that if the status code is 2xx, "
        "the measurement was saved, even with this error present. "
        "Null if no errors.",
        default=None,
    )


@router.post("/submit_measurement/{report_id}", tags=["anonymous_credentials"])
async def submit_measurement(
    report_id: str,
    request: Request,
    submit_request: SubmitMeasurementRequest,
    response: Response,
    asn_cc_reader: ASNCCReaderDep,
    settings: SettingsDep,
    manifest: ManifestDep,
    clickhouse: ClickhouseDep,
    content_encoding: str = Header(default=None),
) -> SubmitMeasurementResponse:
    """
    Submit measurement, using the anonymous credentials protocol to establish a confidence
    layer over the incoming measurements.

    The anonmymous credentials protocol allows us to measure the trustworthiness of a probe without
    revealing personally identifiable information.

    An error will be returned if using a deprecated manifest version

    Note that even if `error` is not null in the response, the measurement might still be processed.

    Assume that:
    - status code 2xx: The measurement was processed and stored, even if not verified
    - status code 4xx or 5xx: the measurement was not processed nor stored
    """
    setnocacheresponse(response)
    try:
        rid_timestamp, test_name, cc, asn, format_cid, rand = report_id.split("_")
    except Exception:
        err_msg = f"Incorrect format: unexpected report_id {report_id[:200]}"
        log.info(err_msg)
        raise HTTPException(
            status_code=400,
            detail={"error": "incorrect_format", "message": err_msg},
        )

    # TODO validate the timestamp?
    good = len(cc) == 2 and test_name.isalnum() and 1 < len(test_name) < 30
    if not good:
        err_msg = f"Incorrect format: unexpected report_id {report_id[:200]}"
        log.info(err_msg)
        raise HTTPException(
            status_code=400,
            detail={"error": "incorrect_format", "message": err_msg},
        )

    try:
        asn_i = int(asn)
    except ValueError:
        err_msg = f"Incorrect format: ASN value not parsable {asn}"
        log.info(err_msg)
        raise HTTPException(
            status_code=400,
            detail={"error": "incorrect_format", "message": err_msg},
        )

    if asn_i == 0:
        log.info("Discarding ASN == 0")
        Metrics.MSMNT_DISCARD_ASN0.inc()
        raise HTTPException(400, detail = {"error" : "asn_0", "message" : "Measurement discarded, ASN == 0"})

    if cc.upper() == "ZZ":
        log.info("Discarding CC == ZZ")
        Metrics.MSMNT_DISCARD_CC_ZZ.inc()
        raise HTTPException(400, detail = {"error" : "cc_zz", "message" : "Measurement discarded, CC == ZZ"})

    # Anonymous credentials verification
    verification_status, submit_error, submit_response = _verify_submit(
        submit_request, manifest, settings
    )

    annotations = submit_request.content.get("annotations") or {}
    platform = annotations.get("platform") or ""
    software_name = submit_request.content.get("software_name") or ""
    software_version = submit_request.content.get("software_version") or ""

    data = submit_request.model_dump()

    # Add verification-related data.
    # use one-letter code for DB, human readable for clients
    data["is_verified"] = verification_status.code
    data_buff = io.BytesIO()
    stream = io.TextIOWrapper(data_buff, "utf-8")
    ujson.dump(data, stream)
    stream.flush()
    data_bin = data_buff.getvalue()

    # Write the whole body of the measurement in a directory based on a 1-hour
    # time window
    now = datetime.now(timezone.utc)
    h = sha512(data_bin).hexdigest()[:16]
    ts = now.strftime("%Y%m%d%H%M%S.%f")

    # msmt_uid is a unique id based on upload time, cc, testname and hash
    msmt_uid = f"{ts}_{cc}_{test_name}_{h}"
    Metrics.MSMNT_RECEIVED_CNT.inc()

    with Metrics.COMPARE_CC_TIMING.time():
        try:
            await run_in_threadpool(
                compare_probe_msmt_cc_asn,
                msmt_uid,
                cc,
                asn,
                request,
                asn_cc_reader,
                clickhouse,
            )
        except Exception:
            log.exception("failed to compared probe_msmt_cc_asn")
            Metrics.COMPARE_CC_FAILURE.inc()

    # Use exponential back off with jitter between retries to avoid choking the fastpath server
    # with many retries at the same time when there's a temporary issue
    client = request.app.state.fastpath_client
    N_RETRIES = 3
    for t in range(N_RETRIES):
        try:
            url = f"{settings.fastpath_url}/{msmt_uid}"

            resp = await run_in_threadpool(client.post, url, data=data)
            with resp:
                resp.raise_for_status()

            return SubmitMeasurementResponse(
                measurement_uid=msmt_uid,
                verification_status=verification_status,
                submit_response=submit_response,
                error=submit_error,
            )

        except Exception as exc:
            log.error(
                f"[Try {t + 1}/{N_RETRIES}] Error trying to send measurement to the fastpath ({settings.fastpath_url}). Error: {exc}"
            )
            sleep_time = random.uniform(0, min(3, 0.3 * 2**t))
            await asyncio.sleep(sleep_time)

    if success:
        try: # Make sure an exception in this function will not trigger a retry
            await run_in_threadpool(
                _check_and_register_geoip_anomaly,
                request,
                asn_cc_reader,
                clickhouse,
                cc,
                asn,
                msmt_uid,
                platform,
                software_name,
                software_version,
            )
        except Exception as e:
            log.error(f"Error checking for geoip anomalies: {e}")

        return SubmitMeasurementResponse(
                measurement_uid=msmt_uid,
                is_verified=is_verified,
                submit_response=submit_response,
            )

    Metrics.SEND_FASTPATH_FAILURE.inc()

    # wasn't possible to send msmnt to fastpath, try to send it to s3
    data_buff.seek(0)
    try:
        await run_in_threadpool(
            request.app.state.s3_client.upload_fileobj,
            data_buff,
            Bucket=settings.failed_reports_bucket,
            Key=report_id,
        )
    except Exception as exc:
        log.error(f"Unable to upload measurement to s3. Error: {exc}")
        Metrics.SEND_S3_FAILURE.inc()

    log.error(f"Unable to send report to fastpath. report_id: {report_id}")
    Metrics.MISSED_MSMNTS.inc()
    return SubmitMeasurementResponse(
        measurement_uid=msmt_uid,
        verification_status=verification_status,
        submit_response=submit_response,
        error=submit_error or "submission_delivery_failed",
    )

def _verify_submit(
    submit_request: SubmitMeasurementRequest,
    manifest: ManifestDep,
    settings: SettingsDep,
) -> tuple[VerificationStatus, str | None, str | None]:
    """
    Run the anonymous credentials verification when the relevant fields are present.

    Returns (verification_status, submit_error, submit_response).
    - "u": unverified (verification did not run)
    - "t": verified
    - "f": verification failed
    """
    # Not intended to be verified: not an error but not verified
    if (
        submit_request.nym is None
        and submit_request.zkp_request is None
        and submit_request.manifest_version is None
        and submit_request.protocol_version is None
    ):
        return (VerificationStatus.UNVERIFIED, None, None)

    # Check manifest version
    if submit_request.manifest_version != manifest.meta.version:
        # TODO We should validate if this is an old manifest or an unknown manifest, for now
        # we treat them as the same error: unknown manifest
        log.error("Old or unknown manifest in submission request")
        return VerificationStatus.UNVERIFIED, "manifest_not_found", None


    # Check anonymous credentials fields are complete
    if (
        submit_request.nym is None
        or submit_request.zkp_request is None
        or submit_request.manifest_version is None
        or submit_request.protocol_version is None
        or "probe_cc" not in submit_request.content
        or "probe_asn" not in submit_request.content
    ):
        log.error("Incomplete anonymous credentials fields in submission request")
        return VerificationStatus.UNVERIFIED, "incomplete_anonc_fields", None

    # Check protocol version
    try:
        probe_version_tup = _parse_version_tuple(submit_request.protocol_version)
        min_version_tup = _parse_version_tuple(
            settings.minimum_anonc_protocol_version
        )

        if probe_version_tup < min_version_tup:
            log.error(f"Probe version too old: {submit_request.protocol_version} < {settings.minimum_anonc_protocol_version}")
            return VerificationStatus.UNVERIFIED, "protocol_version_too_old", None

    except Exception as e:
        log.error(f"Unable to parse version string. probe version = {submit_request.protocol_version}, "
        f"minimum protocol version = {settings.minimum_anonc_protocol_version}. Error: {e}"
        )
        return VerificationStatus.UNVERIFIED, "invalid_protocol_version", None

    # Get the limits in age range and measurement count for this request
    age_range, count_range = get_ranges_from_policy(manifest.manifest.submission_policy, submit_request.content['probe_cc'], submit_request.content['probe_asn'])

    # Run verification
    try:
        protocol_state = ServerState.from_creds(
            manifest.manifest.public_parameters, settings.anonc_secret_key
        )
        submit_response = protocol_state.handle_submit_request(
            submit_request.nym,
            submit_request.zkp_request,
            submit_request.content["probe_cc"],
            submit_request.content["probe_asn"],
            list(age_range),
            list(count_range),
        )
        return (VerificationStatus.VERIFIED, None, submit_response)
    except (DeserializationFailed, ProtocolError, CredentialError) as e:
        log.error(f"ZKP Failed: {e}")
        return (VerificationStatus.FAILED, _anonc_exc_to_str(e), None)
    except Exception as e:
        log.error(f"Unexpected anonc error: {e}")
        return (VerificationStatus.FAILED, "unknown_error", None)


def _parse_version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in version.split("."))

def get_ranges_from_policy(
    policy: List[PolicyEntry], probe_cc: str, probe_asn: str
) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """
    Gets the age and measurement count ranges from the specified policy.

    Matching order: first match in the list wins (highest priority first).

    returns:
    age_range, msm_range
    """

    for item in policy:
        match_cc = item.match.probe_cc
        match_asn = item.match.probe_asn

        cc_ok = match_cc == "*" or match_cc == probe_cc
        asn_ok = match_asn == "*" or match_asn == probe_asn

        if cc_ok and asn_ok:
            return item.policy.age, item.policy.measurement_count

    raise ValueError(
        f"No matching submission_policy entry for probe_cc={probe_cc} probe_asn={probe_asn}"
    )


def _check_and_register_geoip_anomaly(
    request: Request,
    asn_cc_reader: ASNCCReaderDep,
    clickhouse: ClickhouseDep,
    cc: str,
    asn: str,
    msmt_uid: str,
    platform: str,
    software_name: str,
    software_version: str,
) -> None:
    actual_cc, actual_asn = get_cc_asn(request, asn_cc_reader)
    if actual_cc != cc or normalize_asn(actual_asn) != normalize_asn(asn):
        register_geoip_anomaly(
            cc,
            actual_cc,
            asn,
            actual_asn,
            clickhouse,
            msmt_uid,
            platform,
            software_name,
            software_version,
        )
    else:
        Metrics.PROBE_CC_ASN_MATCH.inc()

class CredentialUpdateRequest(BaseModel):
    old_manifest_version: str = Field(
        description="The original manifest version you are trying to update from"
    )
    manifest_version: str = Field(
        description="The up-to-date version of the manifest you used to generate the update request"
    )
    update_request: str = Field(
        description="The ZKP request generated by the anonymous credentials library. "
        "Note that you need to generate this with the new server credentials, "
        "so you might want to update your manifest version to the most recent one"
    )


class CredentialUpdateResponse(BaseModel):
    update_response: str = Field(
        description="The ZKP response generated by the anonymous credentials library"
    )


# TODO implement credential update
# @router.post(
#     "/update_credential",
#     response_model=CredentialUpdateResponse,
#     tags=["anonymous_credentials"],
# )
async def credential_update(
    update_request: CredentialUpdateRequest, session: PostgresSessionDep
) -> CredentialUpdateResponse:
    """
    Update your credentials from an older version to a new version.
    This might be necessary when the manifest is updated and our keys are rotated.
    Before creating your update credentials request you need to update your manifest version
    by calling `/api/v1/manifest`
    """

    # TODO we need to find a way to keep track of older private keys to support this endpoint
    raise NotImplementedError("Credential Update is not yet implemented")


def _raise_manifest_not_found(version: str):
    raise HTTPException(
        detail={
            "error": "manifest_not_found",
            "message": f"No manifest with version '{version}' was found",
        },
        status_code=status.HTTP_404_NOT_FOUND,
    )


class TorTarget(BaseModel):
    address: str
    fingerprint: str
    name: Optional[str] = ""
    protocol: str
    params: Optional[Dict[str, List[str]]] = None


@router.get(
    "/test-list/tor-targets", tags=["ooniprobe"], response_model=Dict[str, TorTarget]
)
def list_tor_targets(
    request: Request,
    targets: TorTargetsDep,
) -> Dict[str, TorTarget]:
    token = request.headers.get("Authorization")
    if token is None:
        # XXX not actually validated
        pass

    if targets is not None:
        return targets
    log.info("tor-targets: failed to receive tor-targets from s3")
    raise HTTPException(status_code=401, detail="Invalid tor-targets")


class PsiphonServer(BaseModel):
    OnlyAfterAttempts: int
    SkipVerify: bool
    URL: str


class PsiphonConfig(BaseModel):
    ClientPlatform: str
    ClientVersion: str
    EstablishTunnelTimeoutSeconds: int
    LocalHttpProxyPort: int
    LocalSocksProxyPort: int
    PropagationChannelId: str
    RemoteServerListDownloadFilename: str
    RemoteServerListSignaturePublicKey: str
    RemoteServerListURLs: List[PsiphonServer] = []
    SponsorId: str
    TargetApiProtocol: str
    UseIndistinguishableTLS: bool


@router.get("/test-list/psiphon-config", tags=["ooniprobe"], response_model=PsiphonConfig)
def psiphon_config(
    request: Request,
    config: PsiphonConfigDep
    ) -> PsiphonConfig:

    token = request.headers.get("Authorization")
    if token is None:
        # XXX not actually validated
        pass
    if config is not None:
        return config

    log.info("psiphon-config: failed to receive psiphon-config from s3")
    raise HTTPException(status_code=401, detail="Invalid psiphon-config")
