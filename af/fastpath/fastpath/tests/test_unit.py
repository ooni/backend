#
# Fastpath - unit tests
#

from datetime import date

import fastpath.core as fp
import fastpath.s3feeder as s3feeder
import ujson


def test_trivial_id():
    tid = fp.trivial_id(dict(a="🐱"))
    assert tid == "00d1cb49bba274be952c9f701f1e13b8"


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
        "accuracy": 0.0,
        "blocking_general": 0.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


## test_name: tor


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


# # test_name: meek_fronted_requests_test


def test_score_meek():
    # msmt from legacy probes having a list as "input"
    fn = "fastpath/tests/data/meek.json"
    with open(fn) as f:
        msm = ujson.load(f)
    matches = []
    scores = fp.score_measurement(msm, matches)
    assert scores == {
        "blocking_country": 0.0,
        "blocking_general": 1.0,
        "blocking_global": 0.0,
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
    with open("fastpath/tests/data/bug_352.json") as f:
        msm = ujson.load(f)
    matches = []
    scores = fp.score_measurement(msm, matches)
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
    with open("fastpath/tests/data/requests_none.json") as f:
        msm = ujson.load(f)
    matches = []
    scores = fp.score_measurement(msm, matches)
    assert scores == {
        "analysis": {"blocking_type": "dns"},
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_bug_test_keys_None():
    with open("fastpath/tests/data/test_keys_none.json") as f:
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


def test_bug_various_keys_missing():
    msm = {
        "data_format_version": "0.2.0",
        "input": "http://mail.google.com",
        "measurement_start_time": "2021-01-21 09:28:29",
        "report_id": "20210121T092829Z_webconnectivity_US_8075_n1_K8Vv8aSpoYfW3wqf",
        "test_name": "web_connectivity",
        "test_start_time": "2021-01-21 09:28:28",
    }
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
    etr = s3feeder._calculate_etr(
        t0, now, start_day, date(2020, 1, 2), date(2020, 1, 5), -1, 9
    )
    assert etr / 3600 == 4.0
    etr = s3feeder._calculate_etr(
        t0, now, start_day, date(2020, 1, 4), date(2020, 1, 5), 9, 10
    )
    assert etr / 3600 == 1.0
