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
    # The report_id is empty in the test data
    query_exp = "INSERT INTO fastpath ( measurement_uid, report_id, input, probe_cc, probe_asn, test_name, test_start_time, measurement_start_time, scores, platform, anomaly, confirmed, msm_failure, domain, software_name, software_version ) VALUES "
    assert query == query_exp
    assert qparams == [
        [
            "bogus_uid",
            "",
            "vpn://openvpn.riseup/?addr=51.158.144.32:80&transport=tcp&obfs=none",
            "UK",
            4242,
            "openvpn",
            datetime.datetime(2022, 10, 21, 9, 11, 46),
            datetime.datetime(2022, 10, 21, 9, 12, 18),
            '{"blocking_general":0.0,"blocking_global":0.0,"blocking_country":0.0,"blocking_isp":0.0,"blocking_local":0.0,"extra":{"test_runtime":32.003161366}}',
            "",
            "f",
            "f",
            "f",
            "openvpn.riseup",
            "miniooni",
            "3.17.0-alpha",
        ]
    ]

    query, qparams = exe.call_args_list[1].args
    query = query.replace("\n", " ").replace("  ", " ")
    query_exp = "INSERT INTO obs_openvpn ( anomaly, bootstrap_time, confirmed, error, failure, input, measurement_start_time, measurement_uid, obfuscation, platform, probe_asn, probe_cc, probe_network_name, provider, remote, report_id, resolver_asn, resolver_ip, resolver_network_name, software_name, software_version, success, tcp_connect_status_success, test_runtime, test_start_time, transport ) VALUES"
    assert qparams == [
        {
            "anomaly": False,
            "bootstrap_time": 0.37221659,
            "confirmed": "f",
            "error": "",
            "failure": "",
            "input": "vpn://openvpn.riseup/?addr=51.158.144.32:80&transport=tcp&obfs=none",
            "measurement_start_time": datetime.datetime(2022, 10, 21, 9, 12, 18),
            "measurement_uid": "bogus_uid",
            "obfuscation": "none",
            "platform": "",
            "probe_asn": 4242,
            "probe_cc": "UK",
            "probe_network_name": "UltraLettuce Networks S.L.",
            "provider": "riseup",
            "remote": "51.158.144.32:80",
            "report_id": "",
            "resolver_asn": "A3232",
            "resolver_ip": "142.211.2.197",
            "resolver_network_name": "Google LLC",
            "software_name": "miniooni",
            "software_version": "3.17.0-alpha",
            "success": "",
            "tcp_connect_status_success": "t",
            "test_runtime": 32.003161366,
            "test_start_time": datetime.datetime(2022, 10, 21, 9, 11, 46),
            "transport": "tcp",
        },
    ]
