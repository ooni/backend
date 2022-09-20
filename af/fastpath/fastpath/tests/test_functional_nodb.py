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
            "20220914T143834Z_openvpn_ES_29119_n1_FV0tbY8ohK67hFQe",
            "vpn://openvpn.tunnelbear/?addr=212.129.18.154:443&transport=tcp",
            "ES",
            29119,
            "openvpn",
            datetime.datetime(2022, 9, 14, 14, 37),
            datetime.datetime(2022, 9, 14, 14, 37, 33),
            '{"blocking_general":0.0,"blocking_global":0.0,"blocking_country":0.0,"blocking_isp":0.0,"blocking_local":0.0,"extra":{"test_runtime":33.264747693}}',
            "",
            "f",
            "f",
            "f",
            "openvpn.tunnelbear",
            "miniooni",
            "3.16.0-alpha",
        ]
    ]

    query, qparams = exe.call_args_list[1].args
    query = query.replace("\n", " ").replace("  ", " ")
    query_exp = "INSERT INTO obs_openvpn ( anomaly, bootstrap_time, confirmed, error, failure, input, measurement_start_time, measurement_uid, obfuscation, platform, probe_asn, probe_cc, probe_network_name, provider, remote, report_id, resolver_asn, resolver_ip, resolver_network_name, software_name, software_version, success, tcp_connect_status_success, test_runtime, test_start_time, transport ) VALUES"
    #assert query == query_exp
    assert qparams == [
        [
            False,
            1.46414319,
            "f",
            "",
            "",
            "vpn://openvpn.tunnelbear/?addr=212.129.18.154:443&transport=tcp",
            datetime.datetime(2022, 9, 14, 14, 37, 33),
            "bogus_uid",
            "none",
            "",
            29119,
            "ES",
            "ServiHosting Networks S.L.",
            "tunnelbear",
            "212.129.18.154:443",
            "20220914T143834Z_openvpn_ES_29119_n1_FV0tbY8ohK67hFQe",
            "AS15169",
            "172.253.2.197",
            "Google LLC",
            "miniooni",
            "3.16.0-alpha",
            "",
            "t",
            33.264747693,
            "tcp",
        ]
    ]
