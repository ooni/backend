"""
Functional tests with a mocked-out Clickhouse database
"""

from unittest.mock import Mock
import datetime

import pytest  # debdeps: python3-pytest

import fastpath.core as core
import fastpath.db
from test_unit import loadj


@pytest.fixture(autouse=True, scope="session")
def fprints():
    """Populates the fingerprints global variable"""
    dns_fp = loadj("fingerprints_dns")
    http_fp = loadj("fingerprints_http")
    core.fingerprints = core.prepare_fingerprints(dns_fp, http_fp)
    yield
    core.fingerprints = None


@pytest.fixture(autouse=True, scope="session")
def mock_metrics():
    core.metrics = Mock()


@pytest.fixture(autouse=True, scope="session")
def setup_conf():
    core.conf.no_write_to_db = False
    core.conf.db_uri = None
    core.conf.clickhouse_url = "bogus_clickhouse_uri"


@pytest.fixture(autouse=True)
def mockdb():
    fastpath.db.click_client = Mock()
    yield
    fastpath.db.click_client = None


# # fingerprints # #


def test_prepare_fingerprints():
    dns_fp = loadj("fingerprints_dns")
    http_fp = loadj("fingerprints_http")
    q = core.prepare_fingerprints(dns_fp, http_fp)
    assert core.fingerprints == q


def test_fetch_fingerprints():
    dns_fp, http_fp = fastpath.db.fetch_fingerprints()

    exe = fastpath.db.click_client.execute
    assert exe.called_once
    query, qparams = exe.call_args[0]
    query = query.replace("\n", " ").replace("  ", " ")
    query_exp = (
        "INSERT INTO fastpath ( measurement_uid, report_id, input, "
        "probe_cc, probe_asn, test_name, test_start_time, measurement_start_time, "
        "scores, platform, anomaly, confirmed, msm_failure, domain, software_name, "
        "software_version, test_version, test_runtime, architecture, engine_name, "
        "engine_version ) VALUES "
    )
    assert query == query_exp
    assert qparams == []


def test_fetch_fingerprints(fprints):
    exe = fastpath.db.click_client.execute
    coldata = (
        ("name", "String"),
        ("scope", "String"),
        ("other_names", "String"),
        ("location_found", "String"),
        ("pattern_type", "String"),
        ("pattern", "String"),
        ("confidence_no_fp", "String"),
        ("expected_countries", "String"),
    )
    exe.return_value = [
        [
            ("ooni.by_4", "isp", "cl.dns_isp_by_mts", "dns", "full", "134.17.0.7", 5, "BY"),
        ],
        coldata,
    ]

    dns_fp, http_fp = fastpath.db.fetch_fingerprints()

    # fetch_fingerprints() issues one query for fingerprints_dns and one for
    # fingerprints_http, so we can only assert it was called, and inspect the
    # last call (the fingerprints_http query) below.
    exe.assert_called()
    query, qparams = exe.call_args[0]
    query = " ".join(query.split())
    assert query == (
        "SELECT name, scope, other_names, location_found, pattern_type, "
        "pattern, confidence_no_fp, expected_countries FROM fingerprints_http"
    )
    assert dns_fp == [
        {
            "confidence_no_fp": 5,
            "expected_countries": "BY",
            "location_found": "dns",
            "name": "ooni.by_4",
            "other_names": "cl.dns_isp_by_mts",
            "pattern": "134.17.0.7",
            "pattern_type": "full",
            "scope": "isp",
        }
    ]


def test_score_web_connectivity_bug_610_2(fprints):
    msm = loadj("web_connectivity_null2")
    core.process_measurement((None, msm, "bogus_uid"))

    exe = fastpath.db.click_client.execute
    exe.assert_called_once()
    query, qparams = exe.call_args[0]
    query = query.replace("\n", " ").replace("  ", " ")
    query_exp = (
        "INSERT INTO fastpath ( measurement_uid, report_id, input, "
        "probe_cc, probe_asn, test_name, test_start_time, measurement_start_time, "
        "scores, platform, anomaly, confirmed, msm_failure, blocking_type, domain, software_name, "
        "software_version, test_version, test_runtime, architecture, engine_name, "
        "engine_version, test_helper_address, test_helper_type, ooni_run_link_id, "
        "is_verified ) VALUES "
    )
    assert query == query_exp
    assert qparams == [
        {
            "measurement_uid": "bogus_uid",
            "report_id": "20220815T190259Z_webconnectivity_IR_197207_n1_OXEdxGds3hbBb6Qd",
            "input": "https://yooz.ir/",
            "probe_cc": "IR",
            "probe_asn": 197207,
            "test_name": "web_connectivity",
            "test_start_time": datetime.datetime(2022, 8, 15, 19, 2, 57),
            "measurement_start_time": datetime.datetime(2022, 8, 15, 19, 4, 21),
            "scores": '{"blocking_general":0.0,"blocking_global":0.0,"blocking_country":0.0,"blocking_isp":0.0,"blocking_local":0.0,"accuracy":0.0}',
            "platform": "android",
            "anomaly": "f",
            "confirmed": "f",
            "msm_failure": "t",
            "blocking_type": "",
            "domain": "yooz.ir",
            "software_name": "ooniprobe-android",
            "software_version": "3.7.0",
            "test_version": "0.4.1",
            "test_runtime": 2.476470708,
            "architecture": "arm",
            "engine_name": "ooniprobe-engine",
            "engine_version": "3.15.2",
            "test_helper_address": "https://0.th.ooni.org",
            "test_helper_type": "https",
            "ooni_run_link_id": None,
            "is_verified" : "u",
        }
    ]


def test_score_browser_web(fprints):
    msm = loadj("browser_web")
    core.process_measurement((None, msm, "bogus_uid"))

    exe = fastpath.db.click_client.execute
    exe.assert_called_once()
    query, qparams = exe.call_args[0]
    query = query.replace("\n", " ").replace("  ", " ")
    query_exp = (
        "INSERT INTO fastpath ( measurement_uid, report_id, input, "
        "probe_cc, probe_asn, test_name, test_start_time, measurement_start_time, "
        "scores, platform, anomaly, confirmed, msm_failure, blocking_type, domain, software_name, "
        "software_version, test_version, test_runtime, architecture, engine_name, "
        "engine_version, test_helper_address, test_helper_type, ooni_run_link_id, "
        "is_verified ) VALUES "
    )
    assert query == query_exp
    assert qparams == [
        {
            "anomaly": "f",
            "architecture": "",
            "blocking_type": "",
            "confirmed": "f",
            "domain": "www.viber.com",
            "engine_name": "",
            "engine_version": "",
            "input": "https://www.viber.com/",
            "measurement_start_time": datetime.datetime(2023, 3, 20, 18, 27, 2),
            "measurement_uid": "bogus_uid",
            "msm_failure": "f",
            "ooni_run_link_id": None,
            "platform": "unset",
            "probe_asn": 577,
            "probe_cc": "CA",
            "report_id": "20230320T182635Z_browserweb_CA_577_n1_k3Fvk1o9okE1w7w7",
            "scores": '{"blocking_general":0.0,"blocking_global":0.0,"blocking_country":0.0,"blocking_isp":0.0,"blocking_local":0.0,"extra":{"browser_name":"chrome","load_time_ms":357.40000000037253}}',
            "software_name": "ooniprobe-web",
            "software_version": "0.1.0",
            "test_helper_address": "",
            "test_helper_type": "",
            "test_name": "browser_web",
            "test_runtime": 0.35740000000037253,
            "test_start_time": datetime.datetime(2023, 3, 20, 18, 26, 35),
            "test_version": "0.1.0",
            "is_verified" : "u",
        },
    ]


# # observations


def test_score_openvpn():
    msm = loadj("openvpn")
    msm_tup = (None, msm, "bogus_uid")
    core.process_measurement(msm_tup)

    exe = fastpath.db.click_client.execute
    assert exe.call_count == 2
    query, qparams = exe.call_args_list[0].args
    query = query.replace("\n", " ").replace("  ", " ")
    query_exp = (
        "INSERT INTO fastpath ( measurement_uid, report_id, input, "
        "probe_cc, probe_asn, test_name, test_start_time, measurement_start_time, "
        "scores, platform, anomaly, confirmed, msm_failure, blocking_type, domain, software_name, "
        "software_version, test_version, test_runtime, architecture, engine_name, "
        "engine_version, test_helper_address, test_helper_type, ooni_run_link_id, "
        "is_verified ) VALUES "
    )
    assert query == query_exp
    assert qparams == [
        {
            "measurement_uid": "bogus_uid",
            "report_id": "",
            "input": "vpn://openvpn.riseup/?addr=198.252.153.109:443&transport=tcp&obfs=obfs4",
            "probe_cc": "RO",
            "probe_asn": 9009,
            "test_name": "openvpn",
            "test_start_time": datetime.datetime(2022, 11, 21, 17, 22, 11),
            "measurement_start_time": datetime.datetime(2022, 11, 21, 17, 22, 49),
            "scores": '{"blocking_general":0.0,"blocking_global":0.0,"blocking_country":0.0,"blocking_isp":0.0,"blocking_local":0.0,"extra":{"test_runtime":37.975210163}}',
            "platform": "linux",
            "anomaly": "f",
            "confirmed": "f",
            "msm_failure": "f",
            "blocking_type": "",
            "domain": "openvpn.riseup",
            "software_name": "miniooni",
            "software_version": "3.17.0-alpha",
            "test_version": "0.0.16",
            "test_runtime": 37.975210163,
            "architecture": "amd64",
            "engine_name": "ooniprobe-engine",
            "engine_version": "3.17.0-alpha",
            "test_helper_address": "",
            "test_helper_type": "",
            "ooni_run_link_id": None,
            "is_verified" : "u",
        }
    ]

    query, qparams = exe.call_args_list[1].args
    assert qparams == [
        {
            "anomaly": False,
            "bootstrap_time": 1.5671859910000001,
            "confirmed": False,
            "failure": "",
            "input": "vpn://openvpn.riseup/?addr=198.252.153.109:443&transport=tcp&obfs=obfs4",
            "last_handshake_transaction_id": 8,
            "measurement_start_time": datetime.datetime(2022, 11, 21, 17, 22, 49),
            "measurement_uid": "bogus_uid",
            "minivpn_version": "(devel)",
            "obfs4_version": "(devel)",
            "obfuscation": "obfs4",
            "platform": "",
            "probe_asn": 9009,
            "probe_cc": "RO",
            "probe_network_name": "M247 Ltd",
            "provider": "riseup",
            "remote": "198.252.153.109:443",
            "report_id": "",
            "resolver_asn": 9009,
            "resolver_ip": "185.45.15.210",
            "resolver_network_name": "M247 Ltd",
            "software_name": "miniooni",
            "software_version": "3.17.0-alpha",
            "success": True,
            "success_handshake": True,
            "success_icmp": True,
            "success_urlgrab": True,
            "test_runtime": 37.975210163,
            "test_start_time": datetime.datetime(2022, 11, 21, 17, 22, 11),
            "transport": "tcp",
        },
    ]

    cols = ", ".join(qparams[0].keys())
    q = query.replace("\n", " ").replace("  ", " ")
    assert q == f"INSERT INTO obs_openvpn ( {cols} ) VALUES "


# # inserts


def _summary_rows(n, bad=()):
    return [dict(measurement_uid=f"uid{i}", bad=i in bad) for i in range(n)]


def test_insert_rows_drops_only_bad_rows(monkeypatch):
    from clickhouse_driver.errors import TypeMismatchError

    inserted = []

    def execute(sql, rows, settings=None):
        if any(r["bad"] for r in rows):
            raise TypeMismatchError("Type mismatch in VALUES section")
        inserted.extend(rows)

    fastpath.db.click_client.execute = Mock(side_effect=execute)
    sleep = Mock()
    monkeypatch.setattr(fastpath.db.time, "sleep", sleep)
    rows = _summary_rows(10_000, bad={17, 9_000})
    assert fastpath.db.insert_rows("INSERT", rows, {}) == 2
    assert len(inserted) == 9_998
    assert {r["measurement_uid"] for r in rows} - {r["measurement_uid"] for r in inserted} == {
        "uid17",
        "uid9000",
    }
    sleep.assert_not_called()


def test_insert_rows_retries_network_errors(monkeypatch):
    from clickhouse_driver.errors import NetworkError

    exe = fastpath.db.click_client.execute
    exe.side_effect = [NetworkError("reset"), EOFError(), None]
    sleep = Mock()
    monkeypatch.setattr(fastpath.db.time, "sleep", sleep)
    rows = _summary_rows(3)
    assert fastpath.db.insert_rows("INSERT", rows, {}) == 0
    assert exe.call_count == 3
    assert all(c.args[1] == rows for c in exe.call_args_list)
    assert [c.args[0] for c in sleep.call_args_list] == [1.0, 2.0]


def test_insert_rows_gives_up(monkeypatch):
    from clickhouse_driver.errors import NetworkError

    exe = fastpath.db.click_client.execute
    exe.side_effect = NetworkError("down")
    monkeypatch.setattr(fastpath.db.time, "sleep", Mock())
    assert fastpath.db.insert_rows("INSERT", _summary_rows(5), {}) == 5
    assert exe.call_count == fastpath.db.INSERT_ATTEMPTS


def test_insert_rows_bisects_server_data_errors(monkeypatch):
    # A data error from the server fails the same way every time: drop only
    # the bad rows, without retrying
    from clickhouse_driver.errors import ServerException

    inserted = []

    def execute(sql, rows, settings=None):
        if any(r["bad"] for r in rows):
            raise ServerException("Value out of range", code=321)
        inserted.extend(rows)

    fastpath.db.click_client.execute = Mock(side_effect=execute)
    sleep = Mock()
    monkeypatch.setattr(fastpath.db.time, "sleep", sleep)
    rows = _summary_rows(1_000, bad={3, 500})
    assert fastpath.db.insert_rows("INSERT", rows, {}) == 2
    assert len(inserted) == 998
    sleep.assert_not_called()


@pytest.mark.parametrize(
    "code",
    [
        242,  # TABLE_IS_READ_ONLY: a replica without Keeper
        394,  # QUERY_WAS_CANCELLED: the server shutting down
        999,  # KEEPER_EXCEPTION
        516,  # AUTHENTICATION_FAILED: keeps the queue backing up so probes fail over
        99999,  # not a code we know
    ],
)
def test_insert_rows_retries_other_server_errors(monkeypatch, code):
    from clickhouse_driver.errors import ServerException

    exe = fastpath.db.click_client.execute
    exe.side_effect = [ServerException("transient", code=code), None]
    sleep = Mock()
    monkeypatch.setattr(fastpath.db.time, "sleep", sleep)
    rows = _summary_rows(3)
    assert fastpath.db.insert_rows("INSERT", rows, {}) == 0
    assert exe.call_count == 2
    assert all(c.args[1] == rows for c in exe.call_args_list)
    assert [c.args[0] for c in sleep.call_args_list] == [1.0]


def test_bad_data_error_codes():
    # ClickHouseError keeps clickhouse-driver's codes and adds the missing ones;
    # the set holds the plain int codes ServerException reports
    codes = fastpath.db.BAD_DATA_ERROR_CODES
    assert len(codes) == 15
    assert all(type(c) is int for c in codes)
    assert fastpath.db.ClickHouseError.TYPE_MISMATCH == 53
    assert {467, 760} <= codes


def test_flush_empty_buffer():
    fastpath.db.fastpath_row_buffer = []
    fastpath.db.flush_fastpath_buffer()


def test_update_fingerprints_retries_after_failure(monkeypatch):
    dns_fp = loadj("fingerprints_dns")
    http_fp = loadj("fingerprints_http")
    now = 1_700_000_000
    monkeypatch.setattr(core.time, "time", lambda: now)
    monkeypatch.setattr(core, "fingerprints_update_time", 0)
    monkeypatch.setattr(core, "fingerprints_loaded", False)
    monkeypatch.setattr(core, "fingerprints", dict(dns=[], http=[]))
    fetch = Mock(side_effect=Exception("clickhouse is down"))
    monkeypatch.setattr(fastpath.db, "fetch_fingerprints", fetch)

    core.update_fingerprints_if_needed()
    assert core.fingerprints == dict(dns=[], http=[])

    # The next attempt comes after the retry delay, not after an hour
    fetch.side_effect = None
    fetch.return_value = (dns_fp, http_fp)
    now += core.FINGERPRINTS_RETRY_SECONDS - 1
    core.update_fingerprints_if_needed()
    assert fetch.call_count == 1
    now += 1
    core.update_fingerprints_if_needed()
    assert fetch.call_count == 2
    assert len(core.fingerprints["http"]) == len(http_fp)

    # Once loaded, they are refreshed hourly
    now += core.FINGERPRINTS_REFRESH_SECONDS - 1
    core.update_fingerprints_if_needed()
    assert fetch.call_count == 2
    now += 1
    core.update_fingerprints_if_needed()
    assert fetch.call_count == 3
