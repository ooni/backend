"""
VPN Services

Insert VPN credentials into database.
"""

import itertools
import logging
from typing import List, TypedDict, Tuple
import io

from fastapi import Request
from typing import Dict, Any
from clickhouse_driver import Client as Clickhouse

from fastapi import HTTPException

from mypy_boto3_s3 import S3Client
from sqlalchemy.orm import Session
import pem
from base64 import b64encode
from datetime import datetime, timezone
from os import urandom

import httpx

from .metrics import Metrics
from .common.config import Settings
from .common.clickhouse_utils import insert_click
from .dependencies import CCReaderDep, ASNReaderDep
from ooniprobe.models import OONIProbeVPNProvider, OONIProbeVPNProviderEndpoint

RISEUP_CA_URL = "https://api.black.riseup.net/ca.crt"
RISEUP_CERT_URL = "https://api.black.riseup.net/3/cert"
RISEUP_ENDPOINT_URL = "https://api.black.riseup.net/3/config/eip-service.json"

log = logging.getLogger(__name__)


class OpenVPNConfig(TypedDict):
    ca: str
    cert: str
    key: str


class OpenVPNEndpoint(TypedDict):
    address: str
    protocol: str
    transport: str


def fetch_riseup_ca() -> str:
    r = httpx.get(RISEUP_CA_URL)
    r.raise_for_status()
    return r.text.strip()


def fetch_riseup_cert() -> str:
    r = httpx.get(RISEUP_CERT_URL)
    r.raise_for_status()
    return r.text.strip()


def fetch_openvpn_config() -> OpenVPNConfig:
    ca = fetch_riseup_ca()
    pem_cert = fetch_riseup_cert()
    key, cert = pem.parse(pem_cert)
    return OpenVPNConfig(ca=ca, cert=cert.as_text(), key=key.as_text())


def fetch_openvpn_endpoints() -> List[OpenVPNEndpoint]:
    endpoints = []

    r = httpx.get(RISEUP_ENDPOINT_URL)
    r.raise_for_status()
    j = r.json()
    for ep in j["gateways"]:
        ip = ep["ip_address"]
        # TODO(art): do we want to store this metadata somewhere?
        # location = ep["location"]
        # hostname = ep["host"]
        for t in ep["capabilities"]["transport"]:
            if t["type"] != "openvpn":
                continue
            for transport, port in itertools.product(t["protocols"], t["ports"]):
                endpoints.append(
                    OpenVPNEndpoint(
                        address=f"{ip}:{port}", protocol="openvpn", transport=transport
                    )
                )
    return endpoints


def format_endpoint(provider_name: str, ep: OONIProbeVPNProviderEndpoint) -> str:
    return f"{ep.protocol}://{provider_name}.corp/?address={ep.address}&transport={ep.transport}"


def upsert_endpoints(
    db: Session, new_endpoints: List[OpenVPNEndpoint], provider: OONIProbeVPNProvider
):
    new_endpoints_map = {
        f'{ep["address"]}-{ep["protocol"]}-{ep["transport"]}': ep
        for ep in new_endpoints
    }
    for endpoint in provider.endpoints:
        key = f"{endpoint.address}-{endpoint.protocol}-{endpoint.transport}"
        if key in new_endpoints_map:
            endpoint.date_updated = datetime.now(timezone.utc)
            new_endpoints_map.pop(key)
        else:
            db.delete(endpoint)

    for ep in new_endpoints_map.values():
        db.add(
            OONIProbeVPNProviderEndpoint(
                date_created=datetime.now(timezone.utc),
                date_updated=datetime.now(timezone.utc),
                protocol=ep["protocol"],
                address=ep["address"],
                transport=ep["transport"],
                provider=provider,
            )
        )


def generate_report_id(test_name, settings: Settings, cc: str, asn_i: int) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cid = settings.collector_id
    rand = b64encode(urandom(12), b"oo").decode()
    stn = test_name.replace("_", "")
    rid = f"{ts}_{stn}_{cc}_{asn_i}_n{cid}_{rand}"
    return rid


def extract_probe_ipaddr(request: Request) -> str:

    real_ip_headers = ["X-Forwarded-For", "X-Real-IP"]

    for h in real_ip_headers:
        if h in request.headers:
            return get_first_ip(request.headers.getlist(h)[0])

    return request.client.host if request.client else ""


def lookup_probe_cc(ipaddr: str, cc_reader: CCReaderDep) -> str:
    resp = cc_reader.country(ipaddr)
    return resp.country.iso_code or "ZZ"


def lookup_probe_network(ipaddr: str, asn_reader: ASNReaderDep) -> Tuple[str, str]:
    resp = asn_reader.asn(ipaddr)

    return (
        "AS{}".format(resp.autonomous_system_number),
        resp.autonomous_system_organization or "0",
    )


def error(msg: str | Dict[str, Any], status_code: int = 400):
    raise HTTPException(status_code=status_code, detail=msg)


def compare_probe_msmt_cc_asn(
    measurement_uid : str,
    cc: str,
    asn: str,
    request: Request,
    cc_reader: CCReaderDep,
    asn_reader: ASNReaderDep,
    clickhouse: Clickhouse
):
    """Compares CC/ASN from measurement with CC/ASN from HTTPS connection ipaddr
    Generates a metric.
    """
    try:
        cc = cc.upper()
        ipaddr = extract_probe_ipaddr(request)
        db_cc = lookup_probe_cc(ipaddr, cc_reader)
        db_asn, _ = lookup_probe_network(ipaddr, asn_reader)

        if db_asn.startswith("AS"):
            db_asn = db_asn[2:]
        if db_cc == cc and db_asn == asn:
            Metrics.PROBE_CC_ASN_MATCH.inc()
        if db_cc != cc:
            Metrics.PROBE_CC_ASN_NO_MATCH.labels(mismatch="cc").inc()
        if db_asn != asn:
            Metrics.PROBE_CC_ASN_NO_MATCH.labels(mismatch="asn").inc()

        if db_asn != asn or db_cc != cc:
            insert_click(
                clickhouse,
                "INSERT INTO geoip_mismatch (measurement_uid, probe_cc, probe_asn, probe_cc, actual_cc, actual_asn) VALUES",
                [(measurement_uid, cc, asn, db_cc, db_asn)],
                max_execution_time=5
                )

    except Exception as e:
        log.error(f"Error comparing msm cc and asn: {e}" )


def get_first_ip(headers: str) -> str:
    """
    parse the first ip from a comma-separated list of ips encoded as a string

    example:
    in: '123.123.123, 1.1.1.1'
    out: '123.123.123'
    """
    return headers.partition(',')[0]

def read_file(s3_client : S3Client, bucket: str, file : str) -> str:
    """
    Reads the content of `file` within `bucket` into a  string

    Useful for reading config files from the s3 bucket
    """
    buff = io.BytesIO()
    s3_client.download_fileobj(bucket, file, buff)
    return buff.getvalue().decode()
