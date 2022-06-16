#!/usr/bin/env python3
"""
Updates asn.mmdb and cc.mmdb in /var/lib/ooniapi/
Runs as a systemd timer.

Monitor logs using: sudo journalctl --identifier ooni_download_geoip
"""

import sys
import gzip
import shutil
import logging

# debdeps: python3-geoip2
import geoip2.database  # type: ignore
from pathlib import Path
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import urlopen, Request

import statsd  # debdeps: python3-statsd

TS = datetime.utcnow().strftime("%Y-%m")
ASN_URL = f"https://download.db-ip.com/free/dbip-asn-lite-{TS}.mmdb.gz"
CC_URL = f"https://download.db-ip.com/free/dbip-country-lite-{TS}.mmdb.gz"

OONI_API_DIR = Path("/var/lib/ooniapi/")

metrics = statsd.StatsClient("127.0.0.1", 8125, prefix="ooni_download_geoip")
log = logging.getLogger("ooni_download_geoip")

try:
    from systemd.journal import JournalHandler  # debdeps: python3-systemd

    log.addHandler(JournalHandler(SYSLOG_IDENTIFIER="ooni_download_geoip"))
except ImportError:
    pass

log.addHandler(logging.StreamHandler(sys.stdout))
log.setLevel(logging.DEBUG)


def get_request(url):
    req = Request(url)
    # We need to set the user-agent otherwise db-ip gives us a 403
    req.add_header("User-Agent", "ooni-downloader")
    return urlopen(req)


def is_already_updated() -> bool:
    try:
        with (OONI_API_DIR / "geoipdbts").open() as in_file:
            current_ts = in_file.read()
    except FileNotFoundError:
        return False

    return current_ts == TS


def is_latest_available(url: str) -> bool:
    log.info(f"fetching {url}")
    try:
        resp = get_request(url)
        return resp.status == 200
    except HTTPError as err:
        if resp.status == 404:
            log.info(f"{url} hasn't been updated yet")
            return False
        log.info(f"unexpected status code '{err.code}' in {url}")
        return False


def check_geoip_db(path: Path) -> None:
    assert "cc" in path.name or "asn" in path.name, "invalid path"

    with geoip2.database.Reader(str(path)) as reader:
        if "asn" in path.name:
            r1 = reader.asn("8.8.8.8")
            assert r1 is not None, "database file is invalid"
            m = reader.metadata()
            metrics.gauge("geoip_asn_node_cnt", m.node_count)
            metrics.gauge("geoip_asn_epoch", m.build_epoch)

        elif "cc" in path.name:
            r2 = reader.country("8.8.8.8")
            assert r2 is not None, "database file is invalid"
            m = reader.metadata()
            metrics.gauge("geoip_cc_node_cnt", m.node_count)
            metrics.gauge("geoip_cc_epoch", m.build_epoch)


@metrics.timer("download_geoip")
def download_geoip(url: str, filename: str) -> None:
    log.info(f"Updating geoip database for {url} ({filename})")

    tmp_gz_out = OONI_API_DIR / f"{filename}.gz.tmp"
    tmp_out = OONI_API_DIR / f"{filename}.tmp"

    with get_request(url) as resp:
        with tmp_gz_out.open("wb") as out_file:
            shutil.copyfileobj(resp, out_file)
    with gzip.open(str(tmp_gz_out)) as in_file:
        with tmp_out.open("wb") as out_file:
            shutil.copyfileobj(in_file, out_file)
    tmp_gz_out.unlink()

    try:
        check_geoip_db(tmp_out)
    except Exception as exc:
        log.error(f"consistenty check on the geoip DB failed: {exc}")
        metrics.incr("ooni_geoip_checkfail")
        return

    tmp_out.rename(OONI_API_DIR / filename)


def update_geoip() -> None:
    OONI_API_DIR.mkdir(parents=True, exist_ok=True)
    download_geoip(ASN_URL, "asn.mmdb")
    download_geoip(CC_URL, "cc.mmdb")

    with (OONI_API_DIR / "geoipdbts").open("w") as out_file:
        out_file.write(TS)

    log.info("Updated GeoIP databases")
    metrics.incr("ooni_geoip_updated")


def main():
    if is_already_updated():
        log.debug("Database already updated. Exiting.")
        sys.exit(0)

    if not is_latest_available(ASN_URL) or not is_latest_available(CC_URL):
        log.debug("Update not available yet. Exiting.")
        sys.exit(0)

    update_geoip()


if __name__ == "__main__":
    main()
