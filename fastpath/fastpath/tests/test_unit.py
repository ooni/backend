#
# Fastpath - unit tests
#

from pathlib import Path
from datetime import date

import pytest
import json

from fastpath.utils import trivial_id
from fastpath.db import extract_input_domain
import fastpath.core as fp
import fastpath.core as core
import fastpath.s3feeder as s3feeder
from fastpath.normalize import iter_yaml_msmt_normalized


scores_failed = {
    "accuracy": 0.0,
    "blocking_general": 0.0,
    "blocking_global": 0.0,
    "blocking_country": 0.0,
    "blocking_isp": 0.0,
    "blocking_local": 0.0,
}


def load_yaml(fn):  # returns fd
    f = Path("fastpath/tests/data") / fn
    return f.with_suffix(".yaml").open("rb")


def loadj(fn):
    f = Path("fastpath/tests/data") / fn
    t = f.with_suffix(".json").read_text()
    return json.loads(t)


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
    assert g(dict(x=dict()), "x", "y", default="v") == "v"
    assert g(dict(x=dict(y=None)), "x", "y", default="v") == "v"
    assert g(dict(x=dict(y="22")), "x", "y", default="v") == "22"
    # assert g(dict(x="str"), "x", "y", default="v") == "v"


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


@pytest.fixture
def fprints():
    """Populates the fingerprints global variable"""
    dns_fp = loadj("fingerprints_dns")
    http_fp = loadj("fingerprints_http")
    core.fingerprints = core.prepare_fingerprints(dns_fp, http_fp)
    yield
    core.fingerprints = None


def test_match_fingerprints_no_match(fprints):
    assert fp.fingerprints["dns"]
    assert fp.fingerprints["http"]
    msm = {"probe_cc": "IE", "test_keys": {"requests": []}}
    assert fp.match_fingerprints(msm) == []


def test_match_fingerprints_match_country(fprints):
    msm = {
        "probe_cc": "MY",
        "test_keys": {"requests": [{"response": {"body": "foo ... Makluman/Notification ... foo"}}]},
    }
    matches = fp.match_fingerprints(msm)
    assert matches == [
        {
            "confidence_no_fp": 5,
            "expected_countries": ["MY"],
            "location_found": "body",
            "name": "ooni.my_0",
            "scope": "nat",
        },
    ]
    # {"body_match": "Makluman/Notification", "locality": "country"}]


def test_match_dns_fingerprints_match_country(fprints):
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
    assert matches == [
        {
            "confidence_no_fp": 5,
            "expected_countries": ["TR"],
            "location_found": "dns",
            "name": "ooni.tr_6",
            "other_names": "cl.dns_nat_tr_poison",
            "pattern": "195.175.254.2",
            "pattern_type": "full",
            "scope": "nat",
        },
    ]


def test_match_fingerprints_dict_body(fprints):
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


def test_match_fingerprints_b64_hdr(fprints):
    msm = loadj("web_connectivity_b64_hdr.json")
    assert fp.match_fingerprints(msm) == []


def test_score_web_connectivity_dns_ir_fingerprint(fprints):
    msm = loadj("web_connectivity_ir_fp")
    matches = fp.match_fingerprints(msm)
    assert matches == [
        {
            "confidence_no_fp": 10,
            "expected_countries": ["IR"],
            "location_found": "dns",
            "name": "ooni.ir_10dot10_ipv4_1",
            "other_names": "",
            "pattern": "10.10.34.36",
            "pattern_type": "full",
            "scope": "nat",
        },
    ]
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_general": 2.0,
        "blocking_global": 0.0,
        "blocking_country": 1.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "confirmed": True,
        "analysis": {"blocking_type": "dns"},
        "fingerprints": [
            {
                "confidence_no_fp": 10,
                "expected_countries": ["IR"],
                "location_found": "dns",
                "name": "ooni.ir_10dot10_ipv4_1",
                "scope": "nat",
            }
        ],
    }


# normalization


def test_yaml_normalization_unexpected_bytes():
    fd = load_yaml("dns_n_http_bin_body")
    rfn = "2015-09-03/20150903T223722Z-TR-AS15897-dns_n_http-no_report_id-0.1.0-probe.yaml"
    msms = tuple(iter_yaml_msmt_normalized(fd, "2015-09-03", rfn))
    assert len(msms) == 1
    msm = msms[0]
    json.dumps(msm)  # should not raise


def test_yaml_normalization_binary_city():
    # probe_city in the header is binary. The test measurement is empty
    fd = load_yaml("binary_city")
    rfn = "2015-11-05/bogus_fname.yaml"
    msms = tuple(iter_yaml_msmt_normalized(fd, "2015-11-05", rfn))
    msm = msms[0]
    assert msm["probe_city"] == "Reykjavk"
    json.dumps(msm)  # should not raise


# Follow the order in score_measurement

# # test_name: telegram


def test_score_measurement_telegram_nourl():
    # missing key: test_keys -> requests -> request -> url
    msm = loadj("telegram_nourl")
    scores = fp.score_measurement(msm)
    assert scores == scores_failed


# # test_name: http_header_field_manipulation


def test_score_http_header_field_manipulation_1():
    # failure: requests -> null
    msm = loadj("http_header_field_manipulation_1")
    scores = fp.score_measurement(msm)
    assert scores == scores_failed


def test_score_http_header_field_manipulation_2():
    # failure: requests -> empty list
    msm = loadj("http_header_field_manipulation_2")
    scores = fp.score_measurement(msm)
    assert scores == scores_failed


def test_score_http_header_field_manipulation_3():
    # test helper issue
    msm = loadj("http_header_field_manipulation_3")
    scores = fp.score_measurement(msm)
    assert scores == scores_failed


# # test_name: http_invalid_request_line


def test_score_http_invalid_request_line_1():
    fd = load_yaml("http_invalid_request_line")
    day = "2018-07-27"
    msms = tuple(iter_yaml_msmt_normalized(fd, day, f"{day}/bogus_fname.yaml"))
    msm = msms[0]
    print(msm["test_keys"]["received"])
    json.dumps(msm)  # should not raise


# # test_name: whatsapp


def test_score_whatsapp_failure():
    # Before 2022-12-02 we expected HTTP code 302
    msm = loadj("whatsapp")
    scores = fp.score_measurement(msm)
    assert scores == {
        "analysis": {
            "registration_server_accessible": True,
            "whatsapp_endpoints_accessible": True,
            "whatsapp_web_accessible": True,
        },
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


# # test_name: vanilla_tor


def test_score_vanilla_tor():
    # https://github.com/ooni/backend/issues/608
    msm = loadj("vanilla_tor")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 0.98,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_score_vanilla_tor_ok():
    # https://github.com/ooni/backend/issues/608
    msm = loadj("vanilla_tor_ok")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }

# # test_name: web_connectivity


def test_score_measurement_simple(fprints):
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


def test_is_confirmed():
    matched = core.Fingerprint(expected_countries=["IT"], scope="bogus")
    assert core.is_confirmed("IT", matched)

    matched = core.Fingerprint(expected_countries=["FR"], scope="bogus")
    assert not core.is_confirmed("IT", matched)

    # Do not match ZZ
    matched = core.Fingerprint(expected_countries=["ZZ"], scope="bogus")
    assert not core.is_confirmed("ZZ", matched)

    matched = core.Fingerprint(expected_countries=[], scope="nat")
    assert core.is_confirmed("IT", matched)


def test_score_measurement_confirmed(fprints):
    msm = {
        "input": "foo",
        "measurement_start_time": "",
        "probe_asn": "1",
        "report_id": "123",
        "test_name": "web_connectivity",
        "test_start_time": "",
        "probe_cc": "IT",
        "test_keys": {
            "requests": [{"response": {"body": "GdF Stop Page"}}],
            "blocking": False,
            "accessible": True,
        },
    }
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_country": 1.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "confirmed": True,
        "fingerprints": [
            {
                "confidence_no_fp": 5,
                "expected_countries": ["IT"],
                "location_found": "body",
                "name": "ooni.it_0",
                "scope": "nat",
            }
        ],
    }


def test_score_web_connectivity_odd_hdr(fprints):
    # Header containing a nested dict
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


def test_score_web_connectivity_no_body(fprints):
    # SSL cert verify failed, body key is missing
    msm = loadj("web_connectivity_no_body")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_score_web_connectivity_b64_incorrect(fprints):
    # response->body->data is replaced with a short string with
    # incorrect padding
    msm = loadj("web_connectivity_b64_incorrect")
    scores = fp.score_measurement(msm)
    assert scores


def test_score_web_connectivity_bug_610(fprints):
    msm = loadj("web_connectivity_null")
    scores = fp.score_measurement(msm)
    assert scores == scores_failed


def test_score_web_connectivity_bug_610_2(fprints):
    msm = loadj("web_connectivity_null2")
    scores = fp.score_measurement(msm)
    assert scores == scores_failed


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


# # test_name: signal


def test_score_signal():
    # https://explorer.ooni.org/measurement/20221118T104419Z_signal_IT_30722_n1_Q02UUAiiHlVU0VE6
    msm = loadj("signal_022")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_score_signal_679():
    # https://explorer.ooni.org/m/20230530180835.892478_US_signal_b091ac0f3794bbcd
    # https://github.com/ooni/backend/issues/679
    msm = loadj("signal_679")
    scores = fp.score_measurement(msm)
    assert scores == {
        "accuracy": 0.0,
        "analysis": {"signal_backend_failure": "android_dns_cache_no_data"},
        "blocking_country": 0.0,
        "blocking_general": 1.0,
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


def test_score_torsf383():
    msm = loadj("torsf_383")
    scores = fp.score_measurement(msm)
    assert scores == {
        "accuracy": 0.0,
        "blocking_country": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_score_openvpn():
    msm = loadj("openvpn")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "extra": {"test_runtime": 37.975210163},
    }


# # test_name: browser_web


def test_score_browser_web():
    msm = loadj("browser_web")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "extra": {"browser_name": "chrome", "load_time_ms": 357.40000000037253},
    }


def test_score_browser_web_error():
    msm = loadj("browser_web_error")
    scores = fp.score_measurement(msm)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "extra": {"browser_name": "chrome", "load_time_ms": 680},
    }


# # Bug tests


def test_bug_backend351(fprints):
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


def test_bug_backend352(fprints):
    # https://github.com/ooni/backend/issues/352
    # https://explorer.ooni.org/measurement/20200302T130853Z_AS197207_WIN8WWfSysccyZSG06Z5AaMJjSzrvxaq7UOiTnasi52k9D77T3?input=https%3A%2F%2Ffa.wikipedia.org
    msm = loadj("bug_352")
    scores = fp.score_measurement(msm)
    assert scores == {
        "analysis": {"blocking_type": "dns"},
        "blocking_general": 2.0,
        "blocking_global": 0.0,
        "blocking_country": 1.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
        "analysis": {"blocking_type": "dns"},
        "confirmed": True,
        "fingerprints": [
            {
                "confidence_no_fp": 10,
                "expected_countries": ["IR"],
                "location_found": "dns",
                "name": "ooni.ir_10dot10_ipv4_1",
                "scope": "nat",
            }
        ],
    }


def test_bug_requests_None(fprints):
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


def test_bug_test_keys_None(fprints):
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


def test_bug_various_keys_missing(fprints):
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


def test_extract_expected_countries():
    for inp, out in [
        ("", []),
        (",RU", ["RU"]),
        ("AU,DE,DK,FR ", ["AU", "DE", "DK", "FR"]),
    ]:
        assert fp.extract_expected_countries(inp) == out


def test_prepare_fingerprints():
    dns_fp = [
        {
            "name": "ooni.by_4",
            "scope": "isp",
            "other_names": "cl.dns_isp_by_mts",
            "location_found": "dns",
            "pattern_type": "full",
            "pattern": "134.17.0.7",
            "confidence_no_fp": 5,
            "expected_countries": "BY",
        }
    ]
    fps = fp.prepare_fingerprints(dns_fp, [])
    assert fps == {
        "dns": [
            {
                "confidence_no_fp": 5,
                "expected_countries": ["BY"],
                "location_found": "dns",
                "name": "ooni.by_4",
                "other_names": "cl.dns_isp_by_mts",
                "pattern": "134.17.0.7",
                "pattern_type": "full",
                "scope": "isp",
            }
        ],
        "http": [],
    }
