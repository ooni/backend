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
    core.setup_fingerprints()
    yield
    core.fingerprint = None


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


def test_score_web_connectivity_bug_610_2(fprints):
    msm = loadj("web_connectivity_null2")
    core.process_measurement((None, msm, "bogus_uid"))

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
            "platform": "",
            "anomaly": "f",
            "confirmed": "f",
            "msm_failure": "t",
            "domain": "yooz.ir",
            "software_name": "ooniprobe-android",
            "software_version": "3.7.0",
            "test_version": "0.4.1",
            "test_runtime": 2.476470708,
            "architecture": "arm",
            "engine_name": "ooniprobe-engine",
            "engine_version": "3.15.2",
        }
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
        "scores, platform, anomaly, confirmed, msm_failure, domain, software_name, "
        "software_version, test_version, test_runtime, architecture, engine_name, "
        "engine_version ) VALUES "
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
            "platform": "",
            "anomaly": "f",
            "confirmed": "f",
            "msm_failure": "f",
            "domain": "openvpn.riseup",
            "software_name": "miniooni",
            "software_version": "3.17.0-alpha",
            "test_version": "0.0.16",
            "test_runtime": 37.975210163,
            "architecture": "amd64",
            "engine_name": "ooniprobe-engine",
            "engine_version": "3.17.0-alpha",
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
