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
    query_exp = "INSERT INTO fastpath ( measurement_uid, report_id, input, probe_cc, probe_asn, test_name, test_start_time, measurement_start_time, scores, platform, anomaly, confirmed, msm_failure, domain, software_name, software_version ) VALUES "
    assert query == query_exp
    assert qparams == [
        [
            "bogus_uid",
            "20220815T190259Z_webconnectivity_IR_197207_n1_OXEdxGds3hbBb6Qd",
            "https://yooz.ir/",
            "IR",
            197207,
            "web_connectivity",
            datetime.datetime(2022, 8, 15, 19, 2, 57),
            datetime.datetime(2022, 8, 15, 19, 4, 21),
            '{"blocking_general":0.0,"blocking_global":0.0,"blocking_country":0.0,"blocking_isp":0.0,"blocking_local":0.0,"accuracy":0.0}',
            "",
            "f",
            "f",
            "t",
            "yooz.ir",
            "ooniprobe-android",
            "3.7.0",
        ]
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
    query_exp = "INSERT INTO fastpath ( measurement_uid, report_id, input, probe_cc, probe_asn, test_name, test_start_time, measurement_start_time, scores, platform, anomaly, confirmed, msm_failure, domain, software_name, software_version ) VALUES "
    assert query == query_exp
    assert qparams == [
        [
            "bogus_uid",
            "",
            "vpn://openvpn.riseup/?addr=198.252.153.109:443&transport=tcp&obfs=obfs4",
            "RO",
            9009,
            "openvpn",
            datetime.datetime(2022, 11, 21, 17, 22, 11),
            datetime.datetime(2022, 11, 21, 17, 22, 49),
            '{"blocking_general":0.0,"blocking_global":0.0,"blocking_country":0.0,"blocking_isp":0.0,"blocking_local":0.0,"extra":{"test_runtime":37.975210163}}',
            "",
            "f",
            "f",
            "f",
            "openvpn.riseup",
            "miniooni",
            "3.17.0-alpha",
        ],
    ]

    query, qparams = exe.call_args_list[1].args
    assert qparams == [
        {
            "anomaly": False,
            "bootstrap_time": 1.5671859910000001,
            "confirmed": False,
            "failure": False,
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
