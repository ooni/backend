#!/usr/bin/env python3
"""
Validate an OONI anonymous-credentials manifest JSON against the Pydantic Manifest model.

Usage:
  python scripts/validate_manifest.py [MANIFEST_URL_OR_PATH]

If the first argument is omitted, the default public manifest URL is used.

You might need to have ooniprobe installed as a dependency. Run with hatch: using `hatch shell`
or `hatch run scripts/validate_manifest.py ...`

Examples:
  python scripts/validate_manifest.py
  python scripts/validate_manifest.py https://ooni-anoncreds-manifests-eu-central-1.s3.eu-central-1.amazonaws.com/manifest.json
  python scripts/validate_manifest.py /path/to/manifest.json

Run from the ooniprobe service directory (or ensure ``ooniprobe`` is importable), e.g.:
  hatch run scripts/validate_manifest.py path/to/manifest
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from urllib.request import urlopen
from pydantic import ValidationError
from ooniprobe.dependencies import Manifest

DEFAULT_MANIFEST_URL = (
    "https://ooni-anoncreds-manifests-eu-central-1.s3.eu-central-1.amazonaws.com/manifest.json"
)

log = logging.getLogger(__name__)


def _load_file(source: str) -> bytes:
    s = source.strip()
    if s.startswith("file://"):
        path = Path(s.strip("file://"))
        return path.read_bytes()
    p = Path(s)
    if p.is_file():
        return p.read_bytes()
    if s.startswith("http://") or s.startswith("https://"):
        with urlopen(s) as resp:
            return resp.read()
    log.error(
        f"Not a readable local file and not an http(s) URL: {source}\n"
        "Use a path like /path/to/manifest.json or https://..."
    )
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Validate manifest JSON, using the current Manifest model",
    )
    parser.add_argument(
        "manifest",
        nargs="?",
        default=DEFAULT_MANIFEST_URL,
        help=f"Manifest URL or local file path (default: {DEFAULT_MANIFEST_URL})",
    )
    args = parser.parse_args()

    try:
        raw = _load_file(args.manifest)
    except Exception as e:
        log.error(f"Failed to fetch manifest: {e}")
        sys.exit(1)

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        log.error(f"Failed to parse manifest: {e}")
        sys.exit(1)

    try:
        Manifest(**data)
    except ValidationError as e:
        log.error(f"Manifest validation failed:\n{e}")
        sys.exit(1)

    print("Manifest valid :)")
    return 0


if __name__ == "__main__":
    main()
