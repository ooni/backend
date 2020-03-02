#
# Fastpath - unit tests
#

import fastpath.core as fp
import ujson


def test_trivial_id():
    msm_jstr, tid = fp.trivial_id(dict(a="🐱"))
    assert len(tid) == 32
    assert tid == "00d1cb49bba274be952c9f701f1e13b8"


def test_trivial_id_2():
    with open("fastpath/tests/data/report_real.json") as f:
        msm = ujson.load(f)
    msm_jstr, tid = fp.trivial_id(msm)
    assert tid == "00b236a79311d1239838bb7431955592"


def test_match_fingerprints_no_match():
    fp.setup_fingerprints()
    msm = {"probe_cc": "IE", "test_keys": {"requests": []}}
    assert fp.match_fingerprints(msm) == []


def test_match_fingerprints_match_country():
    fp.setup_fingerprints()
    msm = {
        "probe_cc": "MY",
        "test_keys": {
            "requests": [
                {"response": {"body": "foo ... Makluman/Notification ... foo"}}
            ]
        },
    }
    matches = fp.match_fingerprints(msm)
    assert matches == [{"body_match": "Makluman/Notification", "locality": "country"}]


def test_match_fingerprints_match_zz():
    fp.setup_fingerprints()
    msm = {
        "probe_cc": "IE",
        "test_keys": {
            "requests": [
                {
                    "response": {
                        "body": "",
                        "headers": {"Server": "Kerio Control Embedded Web Server"},
                    }
                }
            ]
        },
    }
    matches = fp.match_fingerprints(msm)
    assert matches == [
        {
            "header_full": "Kerio Control Embedded Web Server",
            "header_name": "server",
            "locality": "local",
        }
    ], matches


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
    matches = []
    scores = fp.score_measurement(msm, matches)
    assert scores == {
        "input": "foo",
        "measurement_start_time": "",
        "probe_asn": "1",
        "probe_cc": "IE",
        "report_id": "123",
        "test_name": "web_connectivity",
        "test_start_time": "",
        "scores": {
            "blocking_general": 0.0,
            "blocking_global": 0.0,
            "blocking_country": 0.0,
            "blocking_isp": 0.0,
            "blocking_local": 0.0,
        },
    }


def test_score_tor():
    fn = "fastpath/tests/data/tor.json"
    with open(fn) as f:
        msm = ujson.load(f)
    matches = []
    scores = fp.score_measurement(msm, matches)
    assert scores == {
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }

# # Bug tests

def test_bug_backend351():
    # https://api.ooni.io/api/v1/measurement/temp-id-386770148
    with open("fastpath/tests/data/bug_351.json") as f:
        msm = ujson.load(f)
    matches = []
    scores = fp.score_measurement(msm, matches)
    assert scores == {
        "accuracy": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }
