"""
Updates asn.mmdb and cc.mmdb in /var/lib/ooniapi/

"""

import sys
import gzip
import timeit
import shutil
import logging

import geoip2.database 
from pathlib import Path
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import urlopen, Request

from prometheus_client import metrics

from .common.config import Settings

class Metrics:
    GEOIP_ASN_NODE_CNT = metrics.Gauge("geoip_asn_node_cnt", "Count of geoi nodes")
    GEOIP_ASN_EPOCH = metrics.Gauge("geoip_asn_epoch", "Geoip current ASN epoch")
    GEOIP_CC_NODE_CNT = metrics.Gauge("geoip_cc_node_cnt", "Geoip asn node count")
    GEOIP_CC_EPOCH = metrics.Gauge("geoip_cc_epoch", "Geoip current CC epoch")
    GEOIP_CHECKFAIL = metrics.Counter("ooni_geoip_checkfail", "How many times did the check fail in geo ip fail")
    GEOIP_UPDATED = metrics.Counter("ooni_geoip_updated", "How many times was the geoip database updated")
    GEOIP_DOWNLOAD_TIME = metrics.Histogram("geoip_download_time", "How long it takes to download the DB")


TS = datetime.now(timezone.utc).strftime("%Y-%m")
ASN_URL = f"https://download.db-ip.com/free/dbip-asn-lite-{TS}.mmdb.gz"
CC_URL = f"https://download.db-ip.com/free/dbip-country-lite-{TS}.mmdb.gz"

GEOIP_DB_DIR = Path(Settings.geoip_db_dir)

log = logging.getLogger("ooni_download_geoip")

log.addHandler(logging.StreamHandler(sys.stdout))
log.setLevel(logging.DEBUG)


def get_request(url):
    req = Request(url)
    # We need to set the user-agent otherwise db-ip gives us a 403
    req.add_header("User-Agent", "ooni-downloader")
    return urlopen(req)


def is_already_updated() -> bool:
    try:
        with (GEOIP_DB_DIR / "geoipdbts").open() as in_file:
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
        if resp.status == 404: # type: ignore
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
            Metrics.GEOIP_ASN_NODE_CNT.set(m.node_count)
            Metrics.GEOIP_ASN_EPOCH.set(m.build_epoch)

        elif "cc" in path.name:
            r2 = reader.country("8.8.8.8")
            assert r2 is not None, "database file is invalid"
            m = reader.metadata()
            Metrics.GEOIP_CC_NODE_CNT.set(m.node_count)
            Metrics.GEOIP_CC_EPOCH.set(m.build_epoch)


def download_geoip(url: str, filename: str) -> None:
    start_time = timeit.default_timer() # Start timer
    log.info(f"Updating geoip database for {url} ({filename})")

    tmp_gz_out = GEOIP_DB_DIR / f"{filename}.gz.tmp"
    tmp_out = GEOIP_DB_DIR / f"{filename}.tmp"

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
        Metrics.GEOIP_CHECKFAIL.inc()
        return

    tmp_out.rename(GEOIP_DB_DIR / filename)
    endtime = timeit.default_timer() # End timer
    Metrics.GEOIP_DOWNLOAD_TIME.observe(endtime - start_time)


def update_geoip() -> None:
    GEOIP_DB_DIR.mkdir(parents=True, exist_ok=True)
    download_geoip(ASN_URL, "asn.mmdb")
    download_geoip(CC_URL, "cc.mmdb")

    with (GEOIP_DB_DIR / "geoipdbts").open("w") as out_file:
        out_file.write(TS)

    log.info("Updated GeoIP databases")
    Metrics.GEOIP_UPDATED.inc()


def try_update():
    if is_already_updated():
        log.debug("Database already updated. Exiting.")
        return

    if not is_latest_available(ASN_URL) or not is_latest_available(CC_URL):
        log.debug("Update not available yet. Exiting.")
        return

    update_geoip()
