from typing import Tuple
import json
import time
import ooniprobe.routers.v1.probe_services as ps
from ooniprobe import utils
from ooniprobe.dependencies import CCReaderDep, ASNReaderDep
from ooniprobe.common.clickhouse_utils import query_click_one_row
from clickhouse_driver import Client as Clickhouse
from ..utils import postj

def fake_lookup_probe_network(ipaddr: str, asn_reader: ASNReaderDep) -> Tuple[str, str]:
    return ("AS4242", "Testing Networks")

def fake_lookup_probe_cc(ipaddr: str, cc_reader: CCReaderDep) -> str:
    return "US"

def missing_lookup_probe_network(ipaddr: str, asn_reader: ASNReaderDep):
    return ("AS0", None)

def missing_lookup_probe_cc(ipaddr: str, cc_reader: CCReaderDep) -> str:
    return "ZZ"

def test_geolookup(client, monkeypatch):
    monkeypatch.setattr(ps, "lookup_probe_network", fake_lookup_probe_network)
    monkeypatch.setattr(ps, "lookup_probe_cc", fake_lookup_probe_cc)
    j = dict(
        addresses=["192.33.4.12", "170.247.170.2", "2801:1b8:10::b", "2001:500:2::c"]
    )
    c = client.post("/api/v1/geolookup", json=j).json()
    assert "geolocation" in c
    assert "v" in c
    g = c["geolocation"]

    for ip in j["addresses"]:
        assert g[ip]["cc"] == "US"
        assert g[ip]["asn"] == "AS4242"
        assert g[ip]["as_name"] == "Testing Networks"

def test_missing_geolookup(client, monkeypatch):
    monkeypatch.setattr(ps, "lookup_probe_network", missing_lookup_probe_network)
    monkeypatch.setattr(ps, "lookup_probe_cc", missing_lookup_probe_cc)
    j = dict(
        addresses=["1.2.3.4", "127.0.0.1"]
    )
    c = client.post("/api/v1/geolookup", json=j).json()
    assert "geolocation" in c
    assert "v" in c
    g = c["geolocation"]

    for ip in j["addresses"]:
        assert g[ip]["cc"] == "ZZ"
        assert g[ip]["asn"] == "AS0"
        assert g[ip]["as_name"] == ""

def patched_lookup_probe_cc(ipaddr: str, cc_reader) -> str:
    d = {
        "123.123.123.123": "VE",
        "123.123.123.124": "US",
        "123.123.123.125": "VE",
        "123.123.123.126": "US",
    }

    return d.get(ipaddr, "ZZ")


def patched_lookup_probe_network(ipaddr: str, asn_reader) -> Tuple[str, str]:
    d = {
        "123.123.123.123": ("AS65550", "Testing VE"),
        "123.123.123.124": ("AS65550", "Testing VE 2"),
        "123.123.123.125": ("AS65551", "Testing US"),
        "123.123.123.126": ("AS65551", "Testing US 2"),
    }

    return d.get(ipaddr, ("AS0", ""))

def test_geoip_mismatch(client, clickhouse_db, monkeypatch):

    monkeypatch.setattr(utils, "lookup_probe_cc", patched_lookup_probe_cc)
    monkeypatch.setattr(utils, "lookup_probe_network", patched_lookup_probe_network)

    j = {
        "data_format_version": "0.2.0",
        "format": "json",
        "probe_asn": "AS65550",
        "probe_cc": "VE",
        "software_name": "ooni-integ-test",
        "software_version": "0.0.0",
        "test_name": "web_connectivity",
        "test_start_time": "2020-09-09 14:11:11",
        "test_version": "0.1.0",
    }

    c = postj(
        client,
        "/report",
        j,
    )
    rid = c["report_id"]

    # Clear table before starting
    clickhouse_db.execute("TRUNCATE TABLE faulty_measurements")

    body = {"format": "json", "content": {}}

    # matching cc and asn
    postj(
        client,
        f"/report/{rid}",
        body,
        headers={"X-Forwarded-For": "123.123.123.123"},
    )
    time.sleep(0.1)  # Allow async insert to complete
    r = query_click_one_row(
        clickhouse_db,
        "SELECT count(*) as total FROM faulty_measurements",
        {},
    )

    assert r and r["total"] == 0, r

    # cc mismatch only
    postj(
        client,
        f"/report/{rid}",
        body,
        headers={"X-Forwarded-For": "123.123.123.124"},
    )
    time.sleep(0.1)  # Allow async insert to complete
    r = query_click_one_row(
        clickhouse_db,
        "SELECT count(*) as total FROM faulty_measurements",
        {},
    )
    assert r and r["total"] == 1, r
    check_mismatch(clickhouse_db, "VE", 65550, "US", 65550)

    # ASN mismatch only
    postj(
        client,
        f"/report/{rid}",
        body,
        headers={"X-Forwarded-For": "123.123.123.125"},
    )
    time.sleep(0.1)  # Allow async insert to complete
    r = query_click_one_row(
        clickhouse_db,
        "SELECT count(*) as total FROM faulty_measurements",
        {},
    )
    assert r and r["total"] == 2, r
    check_mismatch(clickhouse_db, "VE", 65550, "VE", 65551)

    # both cc and ASN mismatch
    postj(
        client,
        f"/report/{rid}",
        body,
        headers={"X-Forwarded-For": "123.123.123.126"},
    )
    time.sleep(0.1)  # Allow async insert to complete
    r = query_click_one_row(
        clickhouse_db,
        "SELECT count(*) as total FROM faulty_measurements",
        {},
    )
    assert r and r["total"] == 3, r
    check_mismatch(clickhouse_db, "VE", 65550, "US", 65551)

def check_mismatch(
    clickhouse_db : Clickhouse,
    submission_cc: str,
    submission_asn: int,
    actual_cc: str,
    actual_asn: int,
):
    row = query_click_one_row(
        clickhouse_db,
        """
        SELECT *
        FROM faulty_measurements
        ORDER BY time DESC
        LIMIT 1
        """,
        {},
    )
    assert row is not None
    assert row["type"] == "geoip"
    assert row["probe_cc"] == actual_cc
    assert row["probe_asn"] == actual_asn
    details = json.loads(row["details"])
    assert details["submission_cc"] == submission_cc
    assert details["submission_asn"] == submission_asn
