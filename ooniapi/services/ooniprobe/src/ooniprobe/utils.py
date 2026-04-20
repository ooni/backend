"""
VPN Services

Insert VPN credentials into database.
"""

import io
import itertools
import json
import logging
from base64 import b64encode
from datetime import datetime, timezone
from os import urandom
from typing import Any, Dict, List, Tuple, TypedDict

import requests
import pem
from fastapi import HTTPException, Request
from mypy_boto3_s3 import S3Client
from sqlalchemy.orm import Session

from ooniprobe.models import OONIProbeVPNProvider, OONIProbeVPNProviderEndpoint

from .common.clickhouse_utils import insert_click
from .common.config import Settings
from .common.dependencies import ClickhouseDep
from .common.errors import AddressNotFoundError
from .dependencies import ASNCCReaderDep
from .metrics import Metrics

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
    r = requests.get(RISEUP_CA_URL)
    with r:
        r.raise_for_status()
        return r.text.strip()


def fetch_riseup_cert() -> str:
    r = requests.get(RISEUP_CERT_URL)
    with r:
        r.raise_for_status()
        return r.text.strip()


def fetch_openvpn_config() -> OpenVPNConfig:
    ca = fetch_riseup_ca()
    pem_cert = fetch_riseup_cert()
    key, cert = pem.parse(pem_cert)
    return OpenVPNConfig(ca=ca, cert=cert.as_text(), key=key.as_text())


def fetch_openvpn_endpoints() -> List[OpenVPNEndpoint]:
    endpoints = []

    r = requests.get(RISEUP_ENDPOINT_URL)
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
        f"{ep['address']}-{ep['protocol']}-{ep['transport']}": ep
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


def geolookup_probe(ipaddr: str, asn_cc_reader: ASNCCReaderDep) -> Tuple[str, str, str]:
    entry = asn_cc_reader.get(ipaddr)
    try:
        cc = entry['country']['iso_code']
        asn = entry['autonomous_system_number']
        as_org = entry.get('autonomous_system_organization', "0")
        return (cc, f"AS{asn}", as_org)
    except KeyError:
        raise AddressNotFoundError
    except Exception as e:
        log.error(f"Error looking up {ipaddr}: {e}")
        raise AddressNotFoundError


def error(msg: str | Dict[str, Any], status_code: int = 400):
    raise HTTPException(status_code=status_code, detail=msg)


def compare_probe_msmt_cc_asn(
    measurement_uid: str,
    cc: str,
    asn: str,
    request: Request,
    asn_cc_reader: ASNCCReaderDep,
    clickhouse: ClickhouseDep,
):
    """Compares CC/ASN from measurement with CC/ASN from HTTPS connection ipaddr
    Generates a metric.
    """
    cc = cc.upper()
    ipaddr = extract_probe_ipaddr(request)
    db_cc, db_asn, _ = geolookup_probe(ipaddr, asn_cc_reader)

    if db_asn.startswith("AS"):
        db_asn = db_asn[2:]
    if db_cc == cc and db_asn == asn:
        Metrics.PROBE_CC_ASN_MATCH.inc()
    if db_cc != cc:
        Metrics.PROBE_CC_ASN_NO_MATCH.labels(mismatch="cc").inc()
    if db_asn != asn:
        Metrics.PROBE_CC_ASN_NO_MATCH.labels(mismatch="asn").inc()

    if db_asn != asn or db_cc != cc:
        details = json.dumps(
            {
                "submission_cc": cc,
                "submission_asn": int(asn),
                "measurement_uid": measurement_uid,
            }
        )

        insert_click(
            clickhouse,
            """
            INSERT INTO faulty_measurements (type, probe_cc, probe_asn, details)
            SETTINGS
                async_insert=1,
                wait_for_async_insert=0
            VALUES
            """,
            [("geoip", db_cc, int(db_asn), details)],
            max_execution_time=5,
        )


def get_first_ip(headers: str) -> str:
    """
    parse the first ip from a comma-separated list of ips encoded as a string

    example:
    in: '123.123.123, 1.1.1.1'
    out: '123.123.123'
    """
    return headers.partition(",")[0]


def read_file(s3_client: S3Client, bucket: str, file: str) -> str:
    """
    Reads the content of `file` within `bucket` into a  string

    Useful for reading config files from the s3 bucket
    """
    buff = io.BytesIO()
    s3_client.download_fileobj(bucket, file, buff)
    return buff.getvalue().decode()
