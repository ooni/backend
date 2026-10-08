from csv import DictWriter
from io import StringIO
from sys import byteorder
from os import urandom
import ipaddress
import logging
from base64 import b64encode
from datetime import datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Iterable, List, Optional, Set, Tuple, Union
from fastapi import Response
from fastapi.responses import JSONResponse
from .config import Settings

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


log = logging.getLogger(__name__)


INTERVAL_UNITS = dict(s=1, m=60, h=3600, d=86400)


def cachedjson(interval: str, *a, **kw) -> JSONResponse:
    """Jsonify and add cache expiration"""
    max_age = int(interval[:-1]) * INTERVAL_UNITS[interval[-1]]
    headers = {"Cache-Control": f"max-age={max_age}"}
    return JSONResponse(content=dict(*a, **kw), headers=headers)


def nocachejson(*a, **kw) -> JSONResponse:
    """Jsonify and explicitely prevent caching"""
    headers = {"Cache-Control": "no-cache, max-age=0"}
    return JSONResponse(content=dict(*a, **kw), headers=headers)


def jerror(msg, code=400, **kw) -> JSONResponse:
    headers = {"Cache-Control": "no-cache"}
    return JSONResponse(content=dict(msg=msg, **kw), status_code=code, headers=headers)


def setcacheresponse(interval: str, response: Response):
    max_age = int(interval[:-1]) * INTERVAL_UNITS[interval[-1]]
    response.headers["Cache-Control"] = f"max-age={max_age}"


def setnocacheresponse(response: Response):
    response.headers["Cache-Control"] = "no-cache"


def commasplit(p: str) -> List[str]:
    assert p is not None
    out = set(p.split(","))
    out.discard("")
    return sorted(out)


def convert_to_csv(r) -> str:
    """Convert aggregation result dict/list to CSV"""
    csvf = StringIO()
    if len(r) == 0:
        return ""
    if isinstance(r, dict):
        # 0-dimensional data
        fieldnames = sorted(r.keys())
        writer = DictWriter(csvf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(r)

    else:
        fieldnames = sorted(r[0].keys())
        writer = DictWriter(csvf, fieldnames=fieldnames)
        writer.writeheader()
        for row in r:
            writer.writerow(row)

    result = csvf.getvalue()
    csvf.close()
    return result


def generate_random_intuid(collector_id: str) -> int:
    try:
        collector_id = int(collector_id)
    except ValueError:
        collector_id = 0
    randint = int.from_bytes(urandom(4), byteorder)
    return randint * 100 + collector_id


def generate_report_id(test_name, settings: Settings, cc: str, asn_i: int) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cid = settings.collector_id
    rand = b64encode(urandom(12), b"oo").decode()
    stn = test_name.replace("_", "")
    rid = f"{ts}_{stn}_{cc}_{asn_i}_n{cid}_{rand}"
    return rid

def seconds_until_midnight() -> int:
    now = datetime.now(timezone.utc)
    next_midnight = datetime.combine(
        now.date() + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    )

    ttl_seconds = int((next_midnight - now).total_seconds())

    return max(1, ttl_seconds)


class InvalidForwardedFor(ValueError):
    """An X-Forwarded-For entry our side of the chain wrote isn't an address"""


class TrustedProxies:
    """Proxies whose X-Forwarded-For entries client_ipaddr skips, parsed
    once: single addresses in a set, wider networks in a list"""

    def __init__(self, entries: Iterable[str] = ()):
        self.addresses: Set[IPAddress] = set()
        self.networks: List[IPNetwork] = []
        for entry in entries:
            net = ipaddress.ip_network(entry, strict=False)
            if net.num_addresses == 1:
                self.addresses.add(net.network_address)
            else:
                self.networks.append(net)
        # a proxy writes its own address the same way every time: matching
        # its text skips parsing it
        self.texts: Set[str] = {str(a) for a in self.addresses}

    def __bool__(self) -> bool:
        return bool(self.addresses or self.networks)

    def __contains__(self, ip: IPAddress) -> bool:
        return ip in self.addresses or any(ip in net for net in self.networks)


@lru_cache(maxsize=16)
def trusted_proxies(entries: Tuple[str, ...]) -> TrustedProxies:
    """TrustedProxies for a setting's value, parsed once per value"""
    return TrustedProxies(entries)


def client_ipaddr(forwarded_for: List[str], peer: Optional[str], trusted: TrustedProxies) -> str:
    """The client's address from the X-Forwarded-For headers of a request:
    the last entry, which the ALB or the gateway appended, skipping trusted
    proxies. Without the header, the peer address.

    Raises InvalidForwardedFor if an entry it reaches isn't an IP address
    (our proxies only write addresses) or every entry is a trusted proxy.
    """
    # Take entries off the right one at a time; the ones further left,
    # written by the client, are never looked at
    rest = ",".join(forwarded_for)
    found_trusted = False
    while rest:
        rest, _, entry = rest.rpartition(",")
        entry = entry.strip()
        if not entry:
            continue
        if entry not in trusted.texts:
            try:
                ip = ipaddress.ip_address(entry)
            except ValueError:
                raise InvalidForwardedFor(f"X-Forwarded-For entry {entry!r} is not an IP address: {forwarded_for!r}")
            if ip not in trusted:
                return entry
        found_trusted = True
    if found_trusted:
        raise InvalidForwardedFor(f"X-Forwarded-For has only trusted proxies, no client: {forwarded_for!r}")
    return peer or ""
