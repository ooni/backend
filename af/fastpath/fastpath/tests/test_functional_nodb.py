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
