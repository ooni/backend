"""
VPN Services

Insert VPN credentials into database.
"""

import logging
from typing import Dict, Mapping, TypedDict

import pem
import httpx

RISEUP_CA_URL = "https://api.black.riseup.net/ca.crt"
RISEUP_CERT_URL = "https://api.black.riseup.net/3/cert"


log = logging.getLogger(__name__)


class OpenVPNConfig(TypedDict):
    ca: str
    cert: str
    key: str


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
