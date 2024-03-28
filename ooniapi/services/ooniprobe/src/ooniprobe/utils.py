"""
VPN Services

Insert VPN credentials into database.
"""
import base64
from datetime import datetime, timezone
import itertools
import logging
from typing import Dict, List, Mapping, TypedDict

from sqlalchemy.orm import Session
import pem
import httpx

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
        #location = ep["location"]
        #hostname = ep["host"]
        for t in ep["capabilities"]["transport"]:
            if t["type"] != "openvpn":
                continue
            for transport, port in itertools.product(t["protocols"], t["ports"]):
                endpoints.append(OpenVPNEndpoint(
                    address=f"{ip}:{port}",
                    protocol="openvpn",
                    transport=transport
                ))
    return endpoints

def format_endpoint(provider_name: str, ep: OONIProbeVPNProviderEndpoint) -> str:
    return f"{ep.protocol}://{provider_name}.corp/?address={ep.address}&transport={ep.transport}"

def upsert_endpoints(db: Session, new_endpoints: List[OpenVPNEndpoint], provider: OONIProbeVPNProvider):
    new_endpoints_map = {f'{ep["address"]}-{ep["protocol"]}-{ep["transport"]}': ep for ep in new_endpoints}
    for endpoint in provider.endpoints:
        key = f'{endpoint.address}-{endpoint.protocol}-{endpoint.transport}'
        if key in new_endpoints_map:
            endpoint.date_updated = datetime.now(timezone.utc)
            new_endpoints_map.pop(key)
        else:
            db.delete(endpoint)

    for ep in new_endpoints_map.values():
        db.add(OONIProbeVPNProviderEndpoint(
            date_created=datetime.now(timezone.utc),
            date_updated=datetime.now(timezone.utc),
            protocol=ep["protocol"],
            address=ep["address"],
            transport=ep["transport"],
            provider=provider
        ))