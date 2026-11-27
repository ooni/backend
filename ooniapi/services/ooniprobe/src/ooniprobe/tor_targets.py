"""
Builds the tor-targets list from Tor Browser's built-in bridges and tor's
directory authorities, and uploads it to the config bucket.

Run as a scheduled task: python -m ooniprobe.tor_targets
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

import boto3
import httpx
import ujson

from .common.config import Settings

PT_CONFIG_URL = "https://gitlab.torproject.org/tpo/applications/tor-browser-build/-/raw/main/projects/tor-expert-bundle/pt_config.json"
AUTH_DIRS_URL = (
    "https://gitlab.torproject.org/tpo/core/tor/-/raw/main/src/app/config/auth_dirs.inc"
)

# Protocols the probe's tor experiment knows how to test
BRIDGE_PROTOCOLS = {"obfs4"}

FINGERPRINT_RE = re.compile(r"[0-9A-Fa-f]{40}")
IPV4_ADDR_RE = re.compile(r"\d{1,3}(\.\d{1,3}){3}:\d+")

log = logging.getLogger(__name__)


def parse_bridge_line(line: str) -> Optional[Dict[str, Any]]:
    parts = line.split()
    if len(parts) < 3 or not FINGERPRINT_RE.fullmatch(parts[2]):
        return None
    protocol, address, fingerprint = parts[:3]
    params: Dict[str, List[str]] = {}
    for part in parts[3:]:
        key, sep, value = part.partition("=")
        if sep:
            params.setdefault(key, []).append(value)
    return {
        "address": address,
        "fingerprint": fingerprint,
        "name": "",
        "protocol": protocol,
        "params": params or None,
    }


def parse_bridges(pt_config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    targets = {}
    for lines in pt_config.get("bridges", {}).values():
        for line in lines:
            target = parse_bridge_line(line)
            if target is None or target["protocol"] not in BRIDGE_PROTOCOLS:
                continue
            key = hashlib.sha256(line.encode()).hexdigest()
            targets[key] = target
    return targets


def _auth_dir_entries(text: str) -> List[str]:
    """
    auth_dirs.inc is a list of C string literals, one entry per comma
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    entries, current = [], ""
    for m in re.finditer(r'"([^"]*)"\s*(,)?', text):
        current += m.group(1)
        if m.group(2):
            entries.append(current)
            current = ""
    if current:
        entries.append(current)
    return entries


def parse_auth_dirs(text: str) -> Dict[str, Dict[str, Any]]:
    targets = {}
    for entry in _auth_dir_entries(text):
        tokens = entry.split()
        if not tokens:
            continue
        name, rest = tokens[0], tokens[1:]
        opts = dict(t.split("=", 1) for t in rest if "=" in t)
        addr_idx = next(
            (i for i, t in enumerate(rest) if IPV4_ADDR_RE.fullmatch(t)), None
        )
        if addr_idx is None or "orport" not in opts:
            log.warning(f"skipping unparseable dirauth entry: {entry}")
            continue
        dir_addr = rest[addr_idx]
        fingerprint = "".join(rest[addr_idx + 1 :])
        if not FINGERPRINT_RE.fullmatch(fingerprint):
            log.warning(f"skipping dirauth with bad fingerprint: {entry}")
            continue
        ip = dir_addr.rsplit(":", 1)[0]
        or_addr = f"{ip}:{opts['orport']}"
        for address, protocol in ((or_addr, "or_port_dirauth"), (dir_addr, "dir_port")):
            targets[address] = {
                "address": address,
                "fingerprint": fingerprint,
                "name": name,
                "protocol": protocol,
            }
    return targets


def fetch_tor_targets(client: httpx.Client) -> Dict[str, Dict[str, Any]]:
    resp = client.get(PT_CONFIG_URL)
    resp.raise_for_status()
    bridges = parse_bridges(resp.json())

    resp = client.get(AUTH_DIRS_URL)
    resp.raise_for_status()
    dirauths = parse_auth_dirs(resp.text)

    if not bridges or not dirauths:
        raise ValueError(
            f"incomplete tor targets: {len(bridges)} bridges, {len(dirauths)} dirauths"
        )
    return {**dirauths, **bridges}


def upload(targets: Dict[str, Dict[str, Any]], s3client, bucket: str, key: str):
    body = ujson.dumps(targets, indent=2, sort_keys=True).encode()
    s3client.put_object(
        Bucket=bucket, Key=key, Body=body, ContentType="application/json"
    )


def main():
    settings = Settings()
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        targets = fetch_tor_targets(client)
    upload(targets, boto3.client("s3"), settings.config_bucket, settings.tor_targets)
    log.info(
        f"uploaded {len(targets)} tor targets to s3://{settings.config_bucket}/{settings.tor_targets}"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
