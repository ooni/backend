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
        assert g[ip]["asn"] is None
        assert g[ip]["as_name"] is None


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

    report_req = {
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

    report_body = {
        "format": "json",
        "content": {
            "probe_asn": "AS65550",
            "probe_cc": "VE",
            "software_name": "ooni-integ-test",
            "software_version": "0.0.0",
            "annotations": {"platform": "linux"},
            "test_name": "web_connectivity",
            "test_start_time": "2020-09-09 14:11:11",
            "test_version": "0.1.0",
        },
    }

    c = postj(
        client,
        "/report",
        report_req,
    )
    rid = c["report_id"]

    # matching cc and asn
    postj(
        client,
        f"/report/{rid}",
        report_body,
        headers={"X-Forwarded-For": "123.123.123.123"},
    )
    time.sleep(0.1)  # Allow async insert to complete
    _check_fm_count(clickhouse_db, 0)

    # cc mismatch only
    postj(
        client,
        f"/report/{rid}",
        report_body,
        headers={"X-Forwarded-For": "123.123.123.124"},
    )
    time.sleep(0.1)  # Allow async insert to complete
    _check_fm_count(clickhouse_db, 1)
    _check_mismatch(clickhouse_db, "VE", 65550, "US", 65550)

    # ASN mismatch only
    postj(
        client,
        f"/report/{rid}",
        report_body,
        headers={"X-Forwarded-For": "123.123.123.125"},
    )
    time.sleep(0.1)  # Allow async insert to complete
    _check_fm_count(clickhouse_db, 2)
    _check_mismatch(clickhouse_db, "VE", 65550, "VE", 65551)

    # both cc and ASN mismatch
    postj(
        client,
        f"/report/{rid}",
        report_body,
        headers={"X-Forwarded-For": "123.123.123.126"},
    )
    time.sleep(0.1)  # Allow async insert to complete
    _check_fm_count(clickhouse_db, 3)
    _check_mismatch(clickhouse_db, "VE", 65550, "US", 65551)


@pytest.mark.asyncio
async def test_geoip_mismatch_anoncred(client, clickhouse_db, clean_faulty_measurements, monkeypatch):
    # Use the same patched geoip lookup to force mismatches
    monkeypatch.setattr(utils, "geolookup_probe", patched_geolookup_probe)

    # Open a report for the anoncred submit endpoint
    report_req = make_report_request(probe_cc="VE", probe_asn="AS65550")
    postj(client, "/report", report_req)

    # Create anoncred user and submit_request
    user, manifest_version, emission_day = setup_user(client)
    submit_request = make_submit_request(user, "VE", "AS65550")

    # Build measurement body for `/api/v1/submit_measurement`
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


    # matching cc and asn
    postj(
        client,
        "/api/v1/submit_measurement",
        msm,
        headers={"X-Forwarded-For": "123.123.123.123"},
    )
    time.sleep(0.1)  # Allow async insert to complete
    _check_fm_count(clickhouse_db, 0)

    # cc mismatch only
    postj(
        client,
        "/api/v1/submit_measurement",
        msm,
        headers={"X-Forwarded-For": "123.123.123.124"},
    )
    time.sleep(0.1)  # Allow async insert to complete
    _check_fm_count(clickhouse_db, 1)
    _check_mismatch(clickhouse_db, "VE", 65550, "US", 65550)

    # ASN mismatch only
    postj(
        client,
        "/api/v1/submit_measurement",
        msm,
        headers={"X-Forwarded-For": "123.123.123.125"},
    )
    time.sleep(0.1)  # Allow async insert to complete
    _check_fm_count(clickhouse_db, 2)
    _check_mismatch(clickhouse_db, "VE", 65550, "VE", 65551)

    # both cc and ASN mismatch
    postj(
        client,
        "/api/v1/submit_measurement",
        msm,
        headers={"X-Forwarded-For": "123.123.123.126"},
    )
    time.sleep(0.1)  # Allow async insert to complete
    _check_fm_count(clickhouse_db, 3)
    _check_mismatch(clickhouse_db, "VE", 65550, "US", 65551)

def _check_mismatch(
    clickhouse : Clickhouse,
    submission_cc: str,
    submission_asn: int,
    actual_cc: str,
    actual_asn: int,
):
    row = query_click_one_row(
        clickhouse,
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
    assert "measurement_uid" in details and details['measurement_uid']
    assert "software_name" in details and details['software_name']
    assert "software_version" in details and details['software_version']
    assert "platform" in details and details['platform']

def _check_fm_count(clickhouse_db: Clickhouse, expected: int):
    """
    Checks that there are exactly `expected` faulty measurements entries
    """

    r = query_click_one_row(
        clickhouse_db,
        "SELECT count(*) as total FROM faulty_measurements",
        {},
    )
    assert r and r["total"] == expected, r