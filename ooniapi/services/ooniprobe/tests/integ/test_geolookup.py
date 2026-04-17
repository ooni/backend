from typing import Tuple
import json
import time

import pytest
import ooniprobe.routers.v1.probe_services as ps
from ooniprobe import utils
from ooniprobe.dependencies import ASNCCReaderDep
from ooniprobe.common.clickhouse_utils import query_click_one_row
from clickhouse_driver import Client as Clickhouse
from ..utils import make_submit_request, postj, setup_user
from ..test_anoncred import make_measurement, make_report_request


def fake_geolookup_probe(ipaddr: str, asn_cc_reader: ASNCCReaderDep) -> Tuple:
    return ("US", "AS4242", "Testing Networks")


def missing_geolookup_probe(ipaddr: str, asn_cc_reader: ASNCCReaderDep) -> Tuple[str, str, str]:
    return ("ZZ", None, None)


@pytest.mark.asyncio
async def test_geolookup(client, monkeypatch):
    monkeypatch.setattr(ps, "geolookup_probe", fake_geolookup_probe)
    j = dict(
        addresses=["192.33.4.12", "170.247.170.2", "2801:1b8:10::b", "2001:500:2::c"]
    )
    c = client.post("/api/v1/geolookup", json=j).json()
    assert "geolocation" in c
    assert "v" in c
    g = c["geolocation"]

    for ip in j["addresses"]:
        assert g[ip]["cc"] == "US"
        assert g[ip]["asn"] == 4242
        assert g[ip]["as_name"] == "Testing Networks"


@pytest.mark.asyncio
async def test_missing_geolookup(client, monkeypatch):
    monkeypatch.setattr(ps, "geolookup_probe", missing_geolookup_probe)
    j = dict(addresses=["1.2.3.4", "127.0.0.1"])
    c = client.post("/api/v1/geolookup", json=j).json()
    assert "geolocation" in c
    assert "v" in c
    g = c["geolocation"]

    for ip in j["addresses"]:
        assert g[ip]["cc"] == "ZZ"
        assert g[ip]["asn"] == None
        assert g[ip]["as_name"] == None


def patched_geolookup_probe(ipaddr: str, asn_reader) -> Tuple[str, str, str]:
    d = {
        "123.123.123.123": ("VE", "AS65550", "Testing VE"),
        "123.123.123.124": ("US", "AS65550", "Testing VE 2"),
        "123.123.123.125": ("VE", "AS65551", "Testing US"),
        "123.123.123.126": ("US", "AS65551", "Testing US 2"),
    }

    return d.get(ipaddr, ("AS0", ""))


@pytest.mark.asyncio
async def test_geoip_mismatch(client, clickhouse_db, clean_faulty_measurements, monkeypatch):

    monkeypatch.setattr(utils, "geolookup_probe", patched_geolookup_probe)

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

    # cc mismatch only
    postj(
        client,
        f"/report/{rid}",
        body,
        headers={"X-Forwarded-For": "123.123.123.124"},
    )
    time.sleep(0.1)  # Allow async insert to complete

    # ASN mismatch only
    postj(
        client,
        f"/report/{rid}",
        body,
        headers={"X-Forwarded-For": "123.123.123.125"},
    )
    time.sleep(0.1)  # Allow async insert to complete

    # both cc and ASN mismatch
    postj(
        client,
        f"/report/{rid}",
        body,
        headers={"X-Forwarded-For": "123.123.123.126"},
    )
    time.sleep(0.1)  # Allow async insert to complete


@pytest.mark.asyncio
async def test_geoip_mismatch_anoncred(client, clickhouse_db, clean_faulty_measurements, monkeypatch):
    # Use the same patched geoip lookup to force mismatches
    monkeypatch.setattr(utils, "geolookup_probe", patched_geolookup_probe)

    # Open a report for the anoncred submit endpoint
    report_req = make_report_request(probe_cc="VE", probe_asn="AS65550")
    c = postj(client, "/report", report_req)
    rid = c["report_id"]

    # Create anoncred user and submit_request
    user, manifest_version, emission_day = setup_user(client)
    submit_request = make_submit_request(user, "VE", "AS65550")

    # Build measurement body used by /api/v1/submit_measurement/{rid}
    msm = make_measurement(
        submit_request.nym,
        submit_request.request,
        manifest_version,
        probe_cc="VE",
        probe_asn="AS65550",
    )
    msm_content = msm.setdefault("content", {})
    msm_content["software_name"] = "ooni-integ-test"
    msm_content["software_version"] = "0.0.0"
    msm_content["annotations"] = {"platform": "linux"}


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
        ORDER BY ts DESC
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
