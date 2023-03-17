"""
URL parameter parsers
"""

from datetime import datetime
from dateutil.parser import parse as parse_date
from flask import request
from ipaddress import ip_address as parse_ip_address
from typing import Optional, List
from urllib.parse import urlparse
from werkzeug.exceptions import BadRequest
import re
import string

ostr = Optional[str]


def validate(item: ostr, accepted: str) -> None:
    """Ensure item contains only valid chars or is None"""
    if item is None:
        return
    for c in item:
        if c not in accepted:
            raise ValueError("Invalid characters")


def param_asn(name: str) -> Optional[int]:
    p = request.args.get(name)
    if p:
        if p.startswith("AS"):
            return int(p[2:])

        return int(p)

    return None


def param_asn_m(name="probe_asn") -> List[str]:
    p = request.args.get(name)
    if p is None:
        return []

    try:
        ASNs = commasplit(p)
        out = [i[2:] if i.startswith("AS") else i for i in ASNs]
        [int(i) for i in out]
    except ValueError:
        raise ValueError(f"Invalid ASN value in parameter {name}")
    return out


def param_probe_cc_m(name="probe_cc") -> List[str]:
    p = request.args.get(name)
    if p is None:
        return []
    validate(p, string.ascii_uppercase + ",")
    ccs = commasplit(p)
    for cc in ccs:
        if len(cc) != 2:
            raise ValueError(f"Invalid CC value in parameter {name}")
    return ccs


def param_date(name: str) -> Optional[datetime]:
    p = request.args.get(name)
    if p is None:
        return None
    return parse_date(p)


def param_bool(name: str) -> Optional[bool]:
    p = request.args.get(name)
    if not p:
        return None
    return p.lower() == "true"


def param_test_name_m(name) -> List[str]:
    p = request.args.get(name)
    if p is None:
        return []
    accepted = string.ascii_lowercase + "_,"
    validate(p, accepted)
    out = [i for i in p.split(",") if i != ""]
    out = sorted(set(out))
    return out


def param_lowercase_underscore(name) -> ostr:
    p = request.args.get(name)
    accepted = string.ascii_lowercase + "_"
    validate(p, accepted)
    return p


def param_uppercase(name) -> ostr:
    p = request.args.get(name)
    validate(p, string.ascii_uppercase)
    return p


def param_domain_or_none(name) -> Optional[str]:
    p = request.args.get(name)
    if not p:
        return None
    validate_domain(p, name)
    return p


def commasplit(p: str) -> List[str]:
    assert p is not None
    out = set(p.split(","))
    out.discard("")
    return sorted(out)


def param_domain_m(name="domain") -> List[str]:
    p = request.args.get(name)
    if not p:
        return []
    out = commasplit(p)
    for d in out:
        validate_domain(d, name)
    return out


def param_url(name):
    """Accepts URLs, empty string or None"""
    p = request.args.get(name)
    if not p:
        return p
    url = urlparse(p)
    validate_domain(url.netloc, name)
    return p


def param_report_id_or_none() -> Optional[str]:
    p = request.args.get("report_id")
    if not p:
        return None
    if len(p) < 15 or len(p) > 100:
        raise BadRequest("Invalid report_id field")
    accepted = string.ascii_letters + string.digits + "_"
    validate(p, accepted)
    return p


def param_report_id() -> str:
    rid = param_report_id_or_none()
    if rid is None:
        raise BadRequest("Invalid report_id")
    return rid


def param_input_or_none() -> Optional[str]:
    """Accepts any input format supported or None"""
    p = request.args.get("input")
    if not p:
        return None
    x = p.encode("ascii", "ignore").decode()
    accepted = string.ascii_letters + string.digits + r" :/.[]-_%+(){}=?#&!,$"
    for c in x:
        if c not in accepted:
            raise ValueError("Invalid characters in input field")
    return p


def param_measurement_uid() -> str:
    p = request.args.get("measurement_uid")
    if not p or len(p) < 10 or len(p) > 100:
        raise BadRequest("Invalid measurement_uid field")
    return p


domain_matcher = re.compile(
    r"^(?:[a-zA-Z0-9]"  # First char
    r"(?:[a-zA-Z0-9-_]{0,61}[A-Za-z0-9])?\.)"  # sub domain
    r"+[A-Za-z0-9][A-Za-z0-9-_]{0,61}"  # TLD
    r"[A-Za-z]$"  # TLD, last char
)


def validate_domain(p, name: str) -> None:
    """Validates <domain|ipaddr>[:<port>]"""
    try:
        p = p.encode("idna").decode("ascii")
    except Exception:
        raise ValueError(f"Invalid characters in {name} field")
    if domain_matcher.match(p):
        return

    if ":" in p:
        p, port = p.rsplit(":", 1)
        try:
            int(port)
        except Exception:
            raise ValueError(f"Invalid characters in {name} field")

    if domain_matcher.match(p):
        return

    if p.startswith("[") and p.endswith("]"):
        p = p[1:-1]

    try:
        parse_ip_address(p)
    except Exception:
        raise ValueError(f"Invalid characters in {name} field")
