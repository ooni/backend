#
# Fastpath - unit tests
#

from pathlib import Path
from datetime import date

import pytest
import ujson

from fastpath.utils import trivial_id
from fastpath.db import extract_input_domain
import fastpath.core as fp
import fastpath.s3feeder as s3feeder


def loadj(fn):
    f = Path("fastpath/tests/data") / fn
    t = f.with_suffix(".json").read_text()
    return ujson.loads(t)


def test_trivial_id():
    tid = trivial_id(b"", {"measurement_start_time": "2021-02-03 10:11:12"})
    assert tid == "01202102037f9c2ba4e88f827d61604550760585"


def test_extract_input_domain():
    assert extract_input_domain({}, "") == ("", "")
    assert extract_input_domain({"input": "http://x.org"}, "") == ("http://x.org", "x.org")


def test_extract_input_domain_meek():
    msm = {"input": ["b", "a"]}
    assert extract_input_domain(msm, "meek_fronted_requests_test") == ("{b,a}", "b")


def test_g():
    g = fp.g
    assert g({}, "x", default="v") == "v"


def test_gn():
    gn = fp.gn
    assert gn({}, "x") is None
    assert gn({}, "x", "y") is None
    assert gn({"x": None}, "x", "y") is None
    assert gn({"x": {}}, "x", "y") is None
    assert gn({"x": {"y": None}}, "x", "y") is None
    assert gn({"x": {"y": "v"}}, "x", "y") == "v"
    assert gn({"x": "v"}, "x") == "v"
    assert gn({"x": 0}, "x") == 0
    with pytest.raises(Exception):
        assert gn({"x": []}, "x", "y") is None


def test_g_or():
    assert fp.g_or({}, "x", "y") == "y"
    assert fp.g_or({"x": None}, "x", "y") == "y"
    assert fp.g_or({"x": 0}, "x", "y") == 0


def test_match_fingerprints_no_match():
    fp.setup_fingerprints()
    msm = {"probe_cc": "IE", "test_keys": {"requests": []}}
    assert fp.match_fingerprints(msm) == []


def test_match_fingerprints_match_country():
    fp.setup_fingerprints()
    msm = {
        "probe_cc": "MY",
        "test_keys": {"requests": [{"response": {"body": "foo ... Makluman/Notification ... foo"}}]},
    }
    matches = fp.match_fingerprints(msm)
    assert matches == [{"body_match": "Makluman/Notification", "locality": "country"}]


def test_match_dns_fingerprints_match_country():
    fp.setup_fingerprints()
    msm = {
        "probe_cc": "TR",
        "test_keys": {
            "queries": [
                {
                    "engine": "system",
                    "resolver_hostname": None,
                    "query_type": "A",
                    "hostname": "beeg.com",
                    "answers": [
                        {"hostname": "beeg.com", "answer_type": "CNAME", "ttl": 0},
                        {"ipv4": "195.175.254.2", "answer_type": "A", "ttl": 0},
                    ],
                    "failure": None,
                    "resolver_port": None,
                }
            ]
        },
    }
    matches = fp.match_fingerprints(msm)
    assert matches == [{"dns_full": "195.175.254.2", "locality": "country"}]


def test_match_fingerprints_dict_body():
    fp.setup_fingerprints()
    # from 20200108T054856Z-web_connectivity-20200109T102441Z_AS42610_613KNyjuQqiuloY1a391dhZccSDz9M1MD30P6EpUIWSByjcq4T-AS42610-RU-probe-0.2.0.json
    msm = {
        "probe_cc": "MY",
        "test_keys": {
            "requests": [
                {
                    "response": {
                        "body": {
                            "data": "q82BgAABAAEAAAAAA3d3dwdleGFtcGxlA2NvbQAAAQABwAwAAQABAAA/+AAEXbjYIg==",
                            "format": "base64",
                        }
                    }
                }
            ]
        },
    }
    assert fp.match_fingerprints(msm) == []


# Follow the order in score_measurement

# # test_name: web_connectivity


def test_score_measurement_simple():
    msm = {
        "input": "foo",
        "measurement_start_time": "",
        "probe_asn": "1",
        "report_id": "123",
        "test_name": "web_connectivity",
        "test_start_time": "",
        "probe_cc": "IE",
        "test_keys": {},
    }
    scores = fp.score_measurement(msm)
    assert scores == {
        "accuracy": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_score_measurement_confirmed():
    msm = {
        "input": "foo",
        "measurement_start_time": "",
        "probe_asn": "1",
        "report_id": "123",
        "test_name": "web_connectivity",
        "test_start_time": "",
        "probe_cc": "IT",
        "test_keys": {"requests": [{"response": {"body": "GdF Stop Page"}}]},
    }
    scores = fp.score_measurement(msm)
    assert scores == {
        "accuracy": 0.0,
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_country": 1.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "confirmed": True,
    }


def test_score_web_connectivity_odd_hdr():
    # Header containing a nested dict
    fp.setup_fingerprints()
    msm = loadj("web_connectivity_odd_hdr")
    scores = fp.score_measurement(msm)
    assert scores == {
        "analysis": {"blocking_type": "dns"},
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_score_web_connectivity_no_body():
    # SSL cert verify failed, body key is missing
    fp.setup_fingerprints()
    msm = loadj("web_connectivity_no_body")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


# # test_name: dash


def test_score_dash_no_keys():
    msm = dict(test_name="dash")
    scores = fp.score_measurement(msm)
    assert scores == {
        "accuracy": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


# # test_name: tor


def test_score_tor():
    msm = loadj("tor")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "extra": {"test_runtime": 0.767114298},
    }


def test_score_tor_list():
    # Early experimental msmt
    msm = loadj("tor_list")
    scores = fp.score_measurement(msm)
    assert scores == {
        "accuracy": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


# # test_name: riseupvpn


def test_score_riseupvpn():
    msm = loadj("riseupvpn")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "extra": {"test_runtime": 1.076507343},
    }


# # test_name: meek_fronted_requests_test


def test_score_meek():
    # msmt from legacy probes having a list as "input"
    msm = loadj("meek")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_score_meek2():
    # msmt from legacy probes having a list as "input"
    msm = loadj("meek2")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_score_meek3():
    # msmt from legacy probes having a list as "input"
    msm = loadj("meek3")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 0.5,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


# # test_name http_requests


def test_score_http_requests():
    # failed
    msm = loadj("http_requests_1")
    scores = fp.score_measurement(msm)
    assert scores == {
        "accuracy": 0.0,
        "blocking_country": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


# # test_name: stunreachability


def test_score_stunreachability():
    msm_subset = {
        "test_name": "stunreachability",
        "test_keys": {"endpoint": "stun.l.google.com:19302", "failure": None},
    }
    scores = fp.score_measurement(msm_subset)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "extra": {"endpoint": "stun.l.google.com:19302"},
    }


def test_score_stunreachability_fail():
    # failure, also the endpoint key is missing
    msm_subset = {
        "test_name": "stunreachability",
        "test_keys": {"failure": "boo"},
    }
    scores = fp.score_measurement(msm_subset)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "extra": {"endpoint": None, "failure": "boo"},
    }


# # test_name: torsf


def test_score_torsf():
    msm = loadj("torsf_1")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_score_torsf2():
    msm = loadj("torsf_2")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "extra": {"bootstrap_time": 78.980935917, "test_runtime": 79.196301917},
    }


# # Bug tests


def test_bug_backend351():
    # https://api.ooni.io/api/v1/measurement/temp-id-386770148
    msm = loadj("bug_351")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "analysis": {"blocking_type": "http-failure"},
        "accuracy": 0.0,
    }


def test_bug_backend352():
    # https://github.com/ooni/backend/issues/352
    # https://explorer.ooni.org/measurement/20200302T130853Z_AS197207_WIN8WWfSysccyZSG06Z5AaMJjSzrvxaq7UOiTnasi52k9D77T3?input=https%3A%2F%2Ffa.wikipedia.org
    msm = loadj("bug_352")
    scores = fp.score_measurement(msm)
    assert scores == {
        "analysis": {"blocking_type": "dns"},
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_bug_requests_None():
    # caused traceback:
    # File "/usr/lib/python3.7/dist-packages/fastpath/core.py", line 295, in match_fingerprints
    # for req in test_keys.get("requests", ()):
    # TypeError: 'NoneType' object is not iterable
    msm = loadj("requests_none")
    scores = fp.score_measurement(msm)
    assert scores == {
        "analysis": {"blocking_type": "dns"},
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_bug_test_keys_None():
    msm = loadj("test_keys_none")
    scores = fp.score_measurement(msm)
    assert scores == {
        "accuracy": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_bug_various_keys_missing():
    msm = {
        "data_format_version": "0.2.0",
        "input": "http://mail.google.com",
        "measurement_start_time": "2021-01-21 09:28:29",
        "report_id": "20210121T092829Z_webconnectivity_US_8075_n1_K8Vv8aSpoYfW3wqf",
        "test_name": "web_connectivity",
        "test_start_time": "2021-01-21 09:28:28",
        "probe_cc": "US",
        "test_keys": {},
    }
    scores = fp.score_measurement(msm)
    assert scores == {
        "accuracy": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_s3feeder_eta():
    t0 = 1588200000
    now = t0 + 3600
    start_day = date(2020, 1, 1)
    day = date(2020, 1, 1)
    stop_day = date(2020, 1, 2)

    etr = s3feeder._calculate_etr(t0, now, start_day, day, stop_day, 0, 4)
    assert etr / 3600 == 4
    etr = s3feeder._calculate_etr(t0, now, start_day, day, stop_day, 3, 4)
    assert etr / 3600 == 1
    etr = s3feeder._calculate_etr(t0, now, start_day, date(2020, 1, 2), date(2020, 1, 5), -1, 9)
    assert etr / 3600 == 4.0
    etr = s3feeder._calculate_etr(t0, now, start_day, date(2020, 1, 4), date(2020, 1, 5), 9, 10)
    assert etr / 3600 == 1.0


@pytest.mark.skip(reason="Broken")
def test_get_http_header():
    h = {
        "headers": {"Location": "http://example.com"},
        "headers_list": [["Location", "http://example.com"]],
    }
    assert fp.get_http_header(h, "Location") == ["http://example.com"]

    h = {"headers": {"Location": "http://example.com"}}
    assert fp.get_http_header(h, "Location") == ["http://example.com"]

    h = {}
    assert fp.get_http_header(h, "Location") == []

    h = {
        "headers": {"location": "http://example2.com"},
        "headers_list": [["location", "http://example.com"], ["location", "http://example2.com"]],
    }
    assert fp.get_http_header(h, "Location") == [
        "http://example.com",
        "http://example2.com",
    ]
