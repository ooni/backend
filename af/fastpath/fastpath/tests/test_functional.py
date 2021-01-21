"""
Simulate feeding from the collectors or cans on S3 using a local can
"""
# Format with black -t py37 -l 110 --fast

from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock
import logging
import os
import time

import ujson
import boto3  # debdeps: python3-boto3
import pytest  # debdeps: python3-pytest

import fastpath.core as fp
import fastpath.s3feeder as s3feeder

log = logging.getLogger()

# The fixtures download cans from S3 to a local directory
#
# Use credentials from ~/.aws/config in the block:
# [ooni-data]
# aws_access_key_id = ...
# aws_secret_access_key = ...
#
# Explore bucket from CLI:
# AWS_PROFILE=ooni-data-private aws s3 ls s3://ooni-data-private/canned/2019-07-16/

# TODO: drop the boto3 code and use only s3feeder
BUCKET_NAME = "ooni-data"


@pytest.fixture
def cans():
    """Download interesting cans from S3 to a local directory
    """
    # TODO: move to the more flexible s3msmts where possible
    _cans = dict(
        web_conn_it="2018-05-07/20180501T071932Z-IT-AS198471-web_connectivity-20180506T090836Z_AS198471_gKqEpbg0Ny30ldGCQockbZMJSg9HhFiSizjey5e6JxSEHvzm7j-0.2.0-probe.json.lz4",
        web_conn_cn="2018-05-07/20180506T014008Z-CN-AS4134-web_connectivity-20180506T014010Z_AS4134_ZpxhAVt3iqCjT5bW5CfJspbqUcfO4oZfzDVjCWAu2UuVkibFsv-0.2.0-probe.json.lz4",
        web_conn_30="2019-10-30/web_connectivity.00.tar.lz4",
        telegram="2019-08-29/telegram.0.tar.lz4",
        whatsapp="2019-08-29/whatsapp.0.tar.lz4",
        facebook_messenger="2019-08-29/facebook_messenger.0.tar.lz4",
        facebook_messenger2="2019-10-29/facebook_messenger.0.tar.lz4",
        # telegram="2019-08-29/20190829T105210Z-IR-AS31549-telegram-20190829T105214Z_AS31549_t32ZZ5av3B6yNruRIFhCnuT1dHTnwPk7vwIa9F0TAe064HG4tk-0.2.0-probe.json",
        # fb="2019-06-27/20190627T214121Z-ET-AS24757-facebook_messenger-20190627T214126Z_AS24757_h8g9P5kTmmzyX1VyOjqcVonIbFNujm84l2leMCwC2gX3BI78fI-0.2.0-probe.json",
        hhfm_2019_10_26="2019-10-26/http_header_field_manipulation.0.tar.lz4",
        hhfm_2019_10_27="2019-10-27/http_header_field_manipulation.0.tar.lz4",
        hhfm_2019_10_28="2019-10-28/http_header_field_manipulation.0.tar.lz4",
        hhfm_2019_10_29="2019-10-29/http_header_field_manipulation.0.tar.lz4",
        tor_2018_10_26="2018-10-26/vanilla_tor.0.tar.lz4",
        tor_2019_10_26="2019-10-26/vanilla_tor.0.tar.lz4",
        tor_2019_10_27="2019-10-27/vanilla_tor.0.tar.lz4",
        tor_2019_10_28="2019-10-28/vanilla_tor.0.tar.lz4",
        tor_2019_10_29="2019-10-29/vanilla_tor.0.tar.lz4",
        ndt_2018_10_26="2018-10-26/ndt.0.tar.lz4",
        tcp_connect_2018_10_26="2018-10-26/tcp_connect.0.tar.lz4",
        dash_2019_10_26="2019-10-26/dash.0.tar.lz4",
        dash_2019_10_27="2019-10-27/dash.0.tar.lz4",
        dash_2019_10_28="2019-10-28/dash.0.tar.lz4",
        dash_2019_10_29="2019-10-29/dash.0.tar.lz4",
        meek_2019_10_26="2019-10-26/meek_fronted_requests_test.0.tar.lz4",
        meek_2019_10_27="2019-10-27/meek_fronted_requests_test.0.tar.lz4",
        meek_2019_10_28="2019-10-28/meek_fronted_requests_test.0.tar.lz4",
        meek_2019_10_29="2019-10-29/meek_fronted_requests_test.0.tar.lz4",
        big2858="2019-10-30/20191030T032301Z-BR-AS28573-web_connectivity-20191030T032303Z_AS28573_VzW6UrXrs21YjYWvlk1hyzRqnKlmKNsSntSBGqFCnzFVxVSLQf-0.2.0-probe.json.lz4",
    )
    for k, v in _cans.items():
        _cans[k] = Path("testdata") / v

    to_dload = sorted(f for f in _cans.values() if not f.is_file())
    if not to_dload:
        return _cans

    s3 = s3feeder.create_s3_client()

    for fn in to_dload:
        s3fname = fn.as_posix().replace("testdata", "canned")
        r = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=s3fname)
        assert r["KeyCount"] == 1, fn
        assert r["KeyCount"] == 1, r
        filedesc = r["Contents"][0]
        size = filedesc["Size"]
        print("Downloading can %s size %d MB" % (fn, size / 1024 / 1024))

        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, "wb") as f:
            s3.download_fileobj(BUCKET_NAME, s3fname, f)
        assert size == os.path.getsize(fn)

    return _cans


def s3msmts(test_name, start_date=date(2018, 1, 1), end_date=date(2019, 11, 4)):
    """Fetches cans from S3 and iterates over measurements.
    Detect broken dloads.
    """
    s3 = s3feeder.create_s3_client()
    can_date = start_date
    tpl = "{}/{}.00.tar.lz4" if test_name == "web_connectivity" else "{}/{}.0.tar.lz4"
    while can_date <= end_date:
        # e.g. 2019-10-30/psiphon.0.tar.lz4
        can_fname = tpl.format(can_date.strftime("%Y-%m-%d"), test_name)
        can_date += timedelta(days=1)
        can_local_file = Path("testdata") / can_fname

        s3fname = "canned/" + can_fname
        r = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=s3fname)
        if r["KeyCount"] != 1:
            log.info("Can %s not found. Skipping." % s3fname)
            continue

        s3size = r["Contents"][0]["Size"]
        assert s3size > 0
        ready = can_local_file.is_file() and (can_local_file.stat().st_size == s3size)
        if not ready:
            # Download can
            log.debug("Downloading can %s of size %d MB" % (can_fname, s3size / 1024 / 1024))
            can_local_file.parent.mkdir(exist_ok=True)
            with can_local_file.open("wb") as f:
                s3.download_fileobj(BUCKET_NAME, s3fname, f)
            assert s3size == can_local_file.stat().st_size

        log.debug("Loading %s", s3fname)
        for msm_jstr, msm in s3feeder.load_multiple(can_local_file.as_posix()):
            msm = msm or ujson.loads(msm_jstr)
            if msm.get("report_id", None) is None:
                # Missing or empty report_id
                # https://github.com/ooni/probe-engine/pull/104
                continue
            yield can_fname, msm


def list_cans_on_s3_for_a_day(day, filter=None, bysize=False):
    s3 = s3feeder.create_s3_client()
    fns = s3feeder.list_cans_on_s3_for_a_day(s3, day)
    if bysize:
        fns = sorted(fns, key=lambda i: i[1])
    else:
        fns = sorted(fns)

    for fn, size in fns:
        size = size / float(2 ** 20)
        if filter is None or (filter in fn):
            print(f"{fn:<160} {size} MB")


def disabled_test_list_cans():
    """Used for debugging"""
    f = None  # "psiphon"
    for d in range(30, 31):
        list_cans_on_s3_for_a_day("2019-10-{}".format(d), filter=f, bysize=1)
    assert 0


def log_obj(o):
    log.info(ujson.dumps(o, sort_keys=True, ensure_ascii=False, indent=2))


def _print_msm_node(n, depth=0):
    ind = "  " * depth
    if isinstance(n, list):
        for cnt, i in enumerate(n):
            print("{}{}>".format(ind, cnt))
            _print_msm_node(i, depth + 1)

    elif isinstance(n, dict):
        for k in sorted(n):
            v = n[k]
            if k == "body":
                print("{}{}".format(ind, "body: ..."))
            # elif k == "tor_log":
            #    print("{}{}".format(ind, "tor_log: ..."))
            elif isinstance(v, list) or isinstance(v, dict):
                print("{}{}:".format(ind, k))
                _print_msm_node(n[k], depth + 1)
            else:
                print("{}{}: {}".format(ind, k, v))

    else:
        print(ind, n)


def print_msm(msm):
    """Used for debugging"""
    print("--msmt--")
    if "report_id" in msm:
        print("https://explorer.ooni.org/measurement/{}".format(msm["report_id"]))
    _print_msm_node(msm)
    print("--------")


def load_can(can):
    cnt = 0
    for msm_jstr, msm in s3feeder.load_multiple(can.as_posix()):
        msm = msm or ujson.loads(msm_jstr)
        if msm.get("report_id", None) is None:
            # Missing or empty report_id
            # https://github.com/ooni/probe-engine/pull/104
            continue
        yield cnt, msm
        cnt += 1


# TODO mock out metrics


def setup_module(module):
    fp.conf.devel = True
    fp.conf.update = False
    fp.conf.interact = False
    fp.setup_dirs(fp.conf, Path(os.getcwd()))
    fp.setup_fingerprints()


def test_telegram(cans):
    can = cans["telegram"]
    for msm_n, msm in load_can(can):
        scores = fp.score_measurement(msm, [])
        rid = msm["report_id"]
        if rid == "20190830T002837Z_AS209_3nMvNkLIqSZMLqRiaiQylAuHxu6qpK7rVJcAA9Dv2UpcNMhPH0":
            assert scores == {
                "blocking_general": 1.5,
                "blocking_global": 0.0,
                "blocking_country": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
                "web_failure": None,
                "accessible_endpoints": 10,
                "unreachable_endpoints": 0,
                "http_success_cnt": 0,
                "http_failure_cnt": 0,
            }, msm

        elif rid == "20190829T205910Z_AS45184_0TVMQZLWjkfOdqA5b5nNF1XHrafTD4H01GnVTwvfzfiLyLc45r":
            assert scores == {
                "blocking_general": 1.0,
                "blocking_global": 0.0,
                "blocking_country": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
                "web_failure": "connection_reset",
                "accessible_endpoints": 10,
                "unreachable_endpoints": 0,
                "http_success_cnt": 10,
                "http_failure_cnt": 0,
                "msg": "Telegam failure: connection_reset",
            }
        elif rid == "20190829T210302Z_AS197207_28cN0a47WSIxF3SZlXvceoLCSk3rSkyeg0n07pKGAi7XYyEQXM":
            assert scores == {
                "blocking_general": 3.0,
                "blocking_global": 0.0,
                "blocking_country": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
                "web_failure": "generic_timeout_error",
                "accessible_endpoints": 0,
                "unreachable_endpoints": 10,
                "http_success_cnt": 0,
                "http_failure_cnt": 10,
                "msg": "Telegam failure: generic_timeout_error",
            }
        elif rid == "20190829T220118Z_AS16345_28eP4Hw7PQsLmb4eEPWitNvIZH8utHddaTbWZ9qFcaZudmHPfz":
            assert scores == {
                "blocking_general": 3.0,
                "blocking_global": 0.0,
                "blocking_country": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
                "web_failure": "connect_error",
                "accessible_endpoints": 0,
                "unreachable_endpoints": 10,
                "http_success_cnt": 0,
                "http_failure_cnt": 10,
                "msg": "Telegam failure: connect_error",
            }


def test_whatsapp(cans):
    can = cans["whatsapp"]
    debug = False
    for msm_n, msm in load_can(can):
        rid = msm["report_id"]
        scores = fp.score_measurement(msm, [])
        if rid == "20190830T002828Z_AS209_fDHPMTveZ66kGmktmW8JiGDgqAJRivgmBkZjAVRmFbH92OIlTX":
            # empty test_keys -> requests
            log.error(scores)
            assert scores == {
                "accuracy": 0.0,
                "blocking_country": 0.0,
                "blocking_general": 0.0,
                "blocking_global": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
            }

        elif rid == "20190829T002541Z_AS29119_kyaEYabRxQW6q41n4kPH9aX5cvFEXNheCj1fguSf4js3JydUbr":
            # The probe is reporting a false positive: due to the empty client headers
            # it hits https://www.whatsapp.com/unsupportedbrowser
            assert scores == {
                "blocking_general": 0.0,
                "blocking_global": 0.0,
                "blocking_country": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
                "analysis": {
                    "registration_server_accessible": True,
                    "whatsapp_endpoints_accessible": True,
                    "whatsapp_web_accessible": True,
                },
            }, msm

        # TODO: investigate
        # rid == "20190829T021242Z_AS7575_4Us58f7iaQ6jshRAoGVCXggTqtuV5wLNlkp33GJJS4H8Wg7ssV":
        # rid == "20190829T022402Z_AS9009_5zr5RWPkzRPEG0bhEFoWEEi6QB0arZ4qTO72b5iaKwdo6gzLEw":

        # To inspect the test dataset for false positives run this:
        if debug and scores["blocking_general"] > 0:
            print_msm(msm)
            print(scores)
            raise Exception("debug")


def test_whatsapp_probe_bug(cans):
    # https://github.com/ooni/probe-engine/issues/341
    debug = False
    for can_fn, msm in s3msmts("whatsapp", date(2020, 1, 1), date(2020, 1, 10)):
        scores = fp.score_measurement(msm, [])
        assert scores["blocking_general"] in (0.0, 1.0)
        if "analysis" in scores:
            assert scores["analysis"]["whatsapp_web_accessible"] in (True, False), ujson.dumps(
                msm, indent=1, sort_keys=True
            )
            if debug and scores["blocking_general"] > 0:
                print_msm(msm)
                print(scores)
                raise Exception("debug")


def test_facebook_messenger(cans):
    can = cans["facebook_messenger"]
    debug = False
    for msm_n, msm in load_can(can):
        scores = fp.score_measurement(msm, [])
        if msm["report_id"] != "20190829T105137Z_AS6871_TJfyRlEkm6BaCfszHr06nC0c9UsWjWt8mCxRBw1jr0TeqcHTiC":
            continue

        if msm["report_id"] == "20190829T105137Z_AS6871_TJfyRlEkm6BaCfszHr06nC0c9UsWjWt8mCxRBw1jr0TeqcHTiC":
            # not blocked
            assert scores == {
                "blocking_general": 0.0,
                "blocking_global": 0.0,
                "blocking_country": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
            }, msm

        # TODO: add more

        # To inspect the test dataset for false positives run this:
        elif debug and scores["blocking_general"] > 0:
            print_msm(msm)
            print(scores)

    if debug:
        raise Exception("debug")


@pytest.mark.skip(reason="Client bug in checking Facebook ASN")
def test_facebook_messenger_bug(cans):
    can = cans["facebook_messenger"]
    for msm_n, msm in load_can(can):
        scores = fp.score_measurement(msm, [])
        if msm["report_id"] != "20190829T000015Z_AS137_6FCvPkYvOAPUqKgO8QdllyWXTPXUbUAVV3cA43E6drE0KAe4iO":
            continue

        assert scores == {
            "blocking_general": 0.0,
            "blocking_global": 0.0,
            "blocking_country": 0.0,
            "blocking_isp": 0.0,
            "blocking_local": 0.0,
        }


def test_facebook_messenger_newer(cans):
    can = cans["facebook_messenger2"]  # from 2019-10-29
    blocked_cnt = 0
    debug = False
    for msm_n, msm in load_can(can):
        scores = fp.score_measurement(msm, [])
        rid = msm["report_id"]

        if rid == "20191029T101630Z_AS56040_bBOkNtg65fMfH0iOHiG8lMk4UmERxjfJL20ki33lKlyKjS0FkP":
            # TCP really blocked
            assert scores["blocking_general"] >= 1.0
            continue

        elif rid == "20191029T020948Z_AS50010_ZUPoP3hOdwazqZnzPurdWgfLvoMcDL1qyOHHFtEtISjNWMgkrX":
            # DNS returns mostly 0.0.0.0 - but one connection succeeds
            assert scores["blocking_general"] >= 1.0
            continue

        elif scores["blocking_general"] > 0:
            blocked_cnt += 1
            if debug:
                print_msm(msm)
                print(scores)

    ratio = blocked_cnt / (msm_n + 1) * 100
    assert ratio > 7.656
    assert ratio < 7.657

    # TODO: investigate false positives, impement workarounds
    # and update tests and ratio

    # https://explorer.ooni.org/measurement/20191029T213318Z_AS1257_DA3tEqiSVtfOllWDIXcw6KVJdit0TX9Tiv8y2Xganhlx2iWzzh
    # https://explorer.ooni.org/measurement/20191029T213035Z_AS1257_v8XgIqXZqfZObmToEdeAkjs8R3F6ZPwMIieQJ0ewWdgyG75NiP

    # empty tcp_connect:
    # https://explorer.ooni.org/measurement/20191029T003015Z_AS0_DRQLG75YbuAA24UBvGilpatyq9kPUpbcVLR28JBN8EBfv8CzcT
    # https://explorer.ooni.org/measurement/20191029T153938Z_AS33771_l0QJDcqNE5h0ePNxIbTKXY0Gr4LTJwl2Vg4gvPBeCvhcEisKzT

    # Everything around DNS looks broken but TCP is OK
    # https://explorer.ooni.org/measurement/20191029T213318Z_AS1257_DA3tEqiSVtfOllWDIXcw6KVJdit0TX9Tiv8y2Xganhlx2iWzzh


def test_score_measurement_hhfm_large(cans):
    debug = False
    for d in range(26, 30):
        can = cans["hhfm_2019_10_{}".format(d)]
        for msm_n, msm in load_can(can):
            rid = msm["report_id"]
            scores = fp.score_measurement(msm, [])
            if rid == "20191028T115649Z_AS28573_eIrzDM4njwMjxBi0ODrerI5N03zM7qQoCvl4xpapTccdW0kCRg":
                # Missing the "requests" field
                assert scores["blocking_general"] == 0, scores

            elif rid == "20191027T103751Z_AS0_A7vlqt3Ju8pmWflPxJ3E9NyrWJX47yYzQFJcSw63RBDtDm5ulf":
                assert scores["blocking_general"] == 0, scores

            elif rid == "20191027T143046Z_AS35540_5j5W6Q9Iz2pvVNaBtn2heKVHRDzuPtKNcLfrIhVHTmrgA7kWaT":
                assert scores["blocking_general"] == 0, scores

            elif rid == "20191027T192636Z_AS55430_DXpEUz925f3BS7UWyMPnXL8g8OtyDIF3FArF2z9h1ILMtrc":
                assert scores["blocking_general"] == 0, scores

            elif rid == "20191027T002012Z_AS45595_p2qNg0FmL4d2kIuLQXEn36MbraErPPA5i64eE1e6nLfGluHpLk":
                # Client bug?
                assert scores["blocking_general"] == 0, scores

            elif rid == "20191027T192636Z_AS55430_DXpEUz925f3BS7UWyMPnXL8g8OtyDIF3FArF2z9h1ILMtrcbyb":
                # Success - response code 200
                assert scores["blocking_general"] == 0, scores

            elif rid == "20191029T231841Z_AS1257_sGsZRCxZ8obOSLCVCLppeUSfu1La481EQ6E6MGkGBTgffJBs6t":
                # x-tele2-subid was injected
                assert scores["blocking_general"] > 0, scores
                assert scores["msg"] == "1 unexpected header change"

            elif rid == "20191029T071035Z_AS45629_wwVlbw7hc1jJaP5tBfzICM8S4dBhPJK29V97YzJLpthft1Zo6z":
                # Proxy injecting 3 headers
                assert scores["blocking_general"] > 0, scores

            elif debug and scores["blocking_general"] == 1.1:
                url = "https://explorer.ooni.org/measurement/{}".format(rid)
                print(
                    msm["test_start_time"],
                    msm["probe_cc"],
                    url,
                    msm["test_keys"]["requests"][0].get("failure", None),
                )
                print_msm(msm)
                print(scores)


def disabled_test_score_measurement_hhfm_stats(cans):

    can = cans["hhfm_2019_10_27"]
    # Distribution of request->failure values in this can
    #
    # connection_refused 599
    # connection_refused_error 144
    # connection_reset 67
    # None 29
    # eof_error 18
    # generic_timeout_error 4
    # response_never_received 4
    # network_unreachable 2
    # connect_error 1
    # Total 868

    d = Counter()  # CC:failure type -> count
    s = Counter()  # failure type -> count
    for n, msm in enumerate(load_can(can)):
        rid = msm["report_id"]
        # scores = fp.score_measurement(msm, [])
        cc = msm["probe_cc"]
        fm = msm["test_keys"]["requests"][0].get("failure", "*************")
        if fm is None:
            print_msm(msm)
        url = "https://explorer.ooni.org/measurement/{}".format(rid)
        print(url)
        print(msm["probe_cc"], msm["test_keys"]["requests"][0].get("failure", None))

        d.update(("{}:{}".format(cc, fm),))
        s.update((fm,))

    # for i, c in d.most_common(120):
    #    print(i, c)
    for i, c in s.most_common(120):
        print(i, c)
    print("Total", sum(s.values()))
    assert 0


## test_name: vanilla_tor

def test_score_vanilla_tor_2018(cans):
    can = cans["tor_2018_10_26"]
    timeouts = (
        "20181026T003600Z_AS4134_SIts9rD3mrpgIrxrBy6NY7LHJGsBm2dbV4Q8rOHnFEQVESMqB1",
        "20181026T154843Z_AS57963_GKCdB85BgIqr5frZ2Z8qOXVZgdpNGajLRXSidMeRVWg8Qvto3e",
    )
    for msm_n, msm in load_can(can):
        scores = fp.score_measurement(msm, [])
        rid = msm["report_id"]
        if rid in timeouts:
            # Real timeout
            assert scores["blocking_general"] > 0


def test_score_vanilla_tor(cans):
    cnt = 0
    blocked_cnt = 0
    total_score = 0

    for d in range(26, 30):
        can = cans["tor_2019_10_{}".format(d)]
        for msm_n, msm in load_can(can):
            scores = fp.score_measurement(msm, [])
            rid = msm["report_id"]
            cnt += 1
            if rid == "20191029T012425Z_AS45194_So00Y296Ve6q1TvjOtKqsvH1ieiVF566PlcUUOw4Ia37HGPwPL":
                # timeout
                assert scores["blocking_general"] > 0
                blocked_cnt += 1
                total_score += scores["blocking_general"]

            elif scores["blocking_general"] > 0:
                blocked_cnt += 1
                total_score += scores["blocking_general"]
                # print("https://explorer.ooni.org/measurement/{}".format(rid))
                # print_msm(msm)
                # print(scores)
                # assert 0

    p = blocked_cnt * 100 / cnt
    assert 0.35 < p < 0.36, p
    avg = total_score / cnt
    assert 0.003 < avg < 0.004


## test_name: tor
# Also see test_score_tor() in test_unit.py

def test_score_tor():
    for can_fn, msm in s3msmts("tor", date(2020, 6, 1), date(2020, 6, 12)):
        assert msm["test_name"] == "tor"
        rid = msm["report_id"]
        scores = fp.score_measurement(msm, [])
        print(ujson.dumps(msm, sort_keys=True, indent=2))
        break
        if rid == "20200109T111813Z_AS30722_RZeO9Ix6ET2LJzqGcinrDp1iqrhaGGDCHSwlOoybq2N9kZITQt":
            assert scores == {
                "blocking_general": 0.0,
                "blocking_global": 0.0,
                "blocking_country": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
            }
    assert 0

## test_name: web_connectivity

def test_score_web_connectivity_simple(cans):
    # (rid, inp) -> scores: exact match on scores
    expected = {
        (
            "20191104T000516Z_AS52871_uFya6RnctQPrBVEdxE9uUpOxia9frBkNXkP9ZNmhQPEFoKqJ0l",
            "https://100ko.wordpress.com/",
        ): {
            # unknown_failure
            "scores": {
                "accuracy": 0.0,
                "analysis": {"blocking_type": "http-failure"},
                "blocking_country": 0.0,
                "blocking_general": 1.0,
                "blocking_global": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
            }
        },
        (
            "20191104T032906Z_AS8402_fY9b9V3jLtosTMNJbub1xNvuKBpZwPXTp7df9NLw6Sp4QOnXIz",
            "http://www.ohchr.org/",
        ): {
            "scores": {
                "blocking_country": 0.0,
                "blocking_general": 0.0,
                "blocking_global": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
            }
        },
        (
            "20191101T015523Z_AS0_muvGSfWmgRobU77ZL980XGRTyJ80HC0ubQ5YaPaYiotxiXL6po",
            "http://www.newnownext.com/franchise/the-backlot/",
        ): {
            "scores": {
                "analysis": {"blocking_type": "http-diff"},
                "blocking_country": 0.0,
                "blocking_general": 1.0,
                "blocking_global": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
            }
        },
        (
            "20191101T071829Z_AS0_sq5lk0Y4jhCECrgk2pAgMWlgOczBLDkIb2OE9QnHf1OEOmwOBz",
            "http://www.lingeriebowl.com",
        ): {
            "scores": {
                "analysis": {"blocking_type": "dns"},
                "blocking_country": 0.0,
                "blocking_general": 1.0,
                "blocking_global": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
            }
        },
        ("20191101T071829Z_AS0_sq5lk0Y4jhCECrgk2pAgMWlgOczBLDkIb2OE9QnHf1OEOmwOBz", "http://www.pravda.ru"): {
            # In this msmt title_match is false due to the probe following a redirect.
            # The probe uses:
            # (body_length_match or headers_match or title_match) and (status_code_match != false)
            "scores": {
                "blocking_general": 0.0,
                "blocking_global": 0.0,
                "blocking_country": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
            }
        },
    }


    for can_fn, msm in s3msmts("web_connectivity", start_date=date(2019, 11, 1)):
        rid = msm["report_id"]
        inp = msm["input"]
        scores = fp.score_measurement(msm, [])

        if (rid, inp) not in expected:
            # log.warning(f"https://explorer.ooni.org/measurement/{rid}?input={inp}")
            # log.warning((rid, inp, scores))
            continue

        exp = expected.pop((rid, inp))
        if "scores" in exp:
            assert scores == exp["scores"]

    assert len(expected) == 0, "Not all expected measurements were tested"


def test_score_web_connectivity_with_workers(cans):
    # Run worker processes on a big can
    # Mock out database interactions but write output json
    # files
    can = cans["big2858"]
    expected_cnt = 2858

    assert tuple(fp.conf.msmtdir.glob("*")) == ()
    import fastpath.portable_queue as queue
    import multiprocessing as mp

    fp.db.setup = MagicMock()
    fp.db.trim_old_measurements = MagicMock()
    fp.db._autocommit_conn = MagicMock()

    m1 = MagicMock(name="mycursor")
    mctx = MagicMock(name="mock_ctx")

    # By mocking SQL execute() each workers logs its queries in a dedicated
    # file. We then collect the files to inspect if all inputs were processed.
    def mock_execute(query, *a, **kw):
        try:
            pid = os.getpid()
            wl = fp.conf.outdir / f"{pid}.wlog"
            if wl.is_file():
                log.debug("Loading %s", wl)
                d = ujson.load(wl.open())
            else:
                d = dict(inserted_tids=[], other_queries=[])
            if "INSERT INTO fastpath" in query:
                query_args = a[0]
                assert len(query_args) == 11
                tid = query_args[0]
                d["inserted_tids"].append(tid)
            elif "SELECT pg_notify('fastpath" in query:
                pass
            else:
                d["other_queries"].append(query)
            ujson.dump(d, wl.open("w"))
        except Exception as e:
            log.exception(e)

    mctx.execute = mock_execute
    m1.__enter__ = MagicMock(name="myenter", return_value=mctx)
    fp.db._autocommit_conn.cursor = MagicMock(name="curgen", return_value=m1)

    workers = [mp.Process(target=fp.msm_processor, args=(queue,)) for n in range(4)]
    [t.start() for t in workers]
    for w in workers:
        wl = fp.conf.outdir / f"{w.pid}.wlog"
        if wl.is_file():
            wl.unlink()
        assert w.is_alive()

    for msm_n, msm in load_can(can):
        queue.put((None, msm))
    assert msm_n == expected_cnt - 1

    for w in workers:
        # each worker will receive one terminator message and quit
        queue.put(None)

    while any(w.is_alive() for w in workers):
        log.debug("waiting...")
        time.sleep(0.1)

    assert len(tuple(fp.conf.msmtdir.glob("*"))) == expected_cnt

    all_inserted_tids = set()
    for w in workers:
        wl = fp.conf.outdir / f"{w.pid}.wlog"
        assert wl.is_file(), "The worker did not create a logfile"
        d = ujson.load(wl.open())
        wl.unlink()
        s = set(d["inserted_tids"])
        assert len(s) == len(d["inserted_tids"]), "Duplicate INSERT INTO"
        dup = all_inserted_tids & s
        assert len(dup) == 0, f"{dup} inserted by different workers"
        all_inserted_tids = all_inserted_tids | s

    assert len(all_inserted_tids) == expected_cnt


def test_score_ndt(cans):
    can = cans["ndt_2018_10_26"]
    for msm_n, msm in load_can(can):
        scores = fp.score_measurement(msm, [])
        assert scores == {}  # no scoring yet


def test_score_tcp_connect(cans):
    # tcp_connect msmts are identified by (report_id / input)
    debug = 0
    can = cans["tcp_connect_2018_10_26"]
    for msm_n, msm in load_can(can):
        rid = msm["report_id"]
        inp = msm["input"]
        scores = fp.score_measurement(msm, [])
        if rid == "20181026T000102Z_AS51570_2EslrKCu0NhDQiCIheVDvilWchWShK6GTC7Go6i31VQrGfXRLM":
            if inp == "109.105.109.165:22":
                # generic_timeout_error
                assert scores["blocking_general"] == 0.8

            elif inp == "obfs4 83.212.101.3:50000":
                # connection_refused_error
                assert scores["blocking_general"] == 0.8

            elif inp == "178.209.52.110:22":
                # connect_error
                assert scores["blocking_general"] == 0.8

            elif inp == "obfs4 178.209.52.110:443":
                # tcp_timed_out_error
                assert scores["blocking_general"] == 0.8

        elif debug and scores["blocking_general"] > 0.7:
            print("https://explorer.ooni.org/measurement/{}".format(rid))
            print_msm(msm)
            print(scores)
            assert 0


def test_score_dash(cans):
    # rid -> blocking_general, accuracy
    expected = {
        "20191026T015105Z_AS4837_7vwBtbVmZZqwZhdTHnqHan0Nwa7bi7TeJ789htG3RB91C3eyU1": (
            0.1,
            0.0,
            "blocking_general",
        ),
        "20191026T022317Z_AS17380_ZJGnXdvHl4j1M4xTeskrGhC8SW1KT4buJEjxCsTagCGO2NZeAD": (
            0.1,
            0.0,
            "json_parse_error",
        ),
        "20191026T032159Z_AS20057_xLjBSrTyZjOn6C7pa5BPyUxyBhzWHbSooKQjUY9zcWADnkakIR": (
            0.1,
            0.0,
            "eof_error",
        ),
        "20191026T051350Z_AS44244_9yjPG1UbgIjtAFg9LiTUxVhq7hGuG3tG4yMnvt6gRJTaFdQme6": (
            0.1,
            0.0,
            "json_processing_error",
        ),
        "20191026T071332Z_AS7713_caK9GNyp9ZhN7zL9cg2dg0zGhs44CwHmxZtOyK7B6rBKRaGGMF": (
            0.1,
            0.0,
            "http_request_failed",
        ),
        "20191026T093003Z_AS4837_yHZ0f8Oxyhus9vBKAUa0tA2XMSObIO0frShG6YBieBzY9RiSBg": (
            0.1,
            0.0,
            "connect_error",
        ),
        "20191026T165434Z_AS0_qPbZHZF8VXUWgzlvqT9Jd7ARuHSl2Dq4tPcEq580rgYZGmV5Um": (
            0.1,
            0.0,
            "generic_timeout_error",
        ),
        "20191028T160112Z_AS1640_f4zyjjp5vFcwZkAKPrTokayPRdcXPfdEMRbdo1LmIaLZRile6P": (
            0.1,
            0.0,
            "broken_pipe",
        ),
        "20191029T094043Z_AS49048_qGQxBh6lv26TOfuWfhGcUtz2LZWwboXlfbh058CSF1fOmEUv6Z": (
            0.1,
            0.0,
            "connection_refused",
        ),
    }
    for d in range(26, 30):
        can = cans["dash_2019_10_{}".format(d)]
        for msm_n, msm in load_can(can):
            # input is not set or set to None
            assert msm.get("input", None) is None
            rid = msm["report_id"]
            scores = fp.score_measurement(msm, [])

            if rid in expected:
                exp_bs, exp_acc, exp_fail = expected[rid]
                assert scores["blocking_general"] == exp_bs
                assert scores["accuracy"] == exp_acc
                expected.pop(rid)

    assert len(expected) == 0, expected.keys()


def test_score_meek_fronted_requests_test(cans):
    debug = 0
    for d in range(26, 30):
        can = cans["meek_2019_10_{}".format(d)]
        for msm_n, msm in load_can(can):
            rid = msm["report_id"]
            scores = fp.score_measurement(msm, [])
            if rid == "20191026T110224Z_AS3352_2Iqv4PvPItJ2Z3D46wVRHzesBpdDJZ8xDKH7VKqNTebaiGopDY":
                # response: None
                assert scores["blocking_general"] == 1.0

            elif rid == "20191026T000021Z_AS137_0KaXWBZgn8W6iMfKKhjHJPoPPovChlwxr8dDOh4LxTzHDOKLOq":
                # One response: 404
                assert scores["blocking_general"] == 1.0

            elif rid == "20191026T000034Z_AS42668_vpZnPVKEym0dRgYSxyeZulPvnLtxrh6HXzyMx5tE2f4x26CBwX":
                # 403 hitting cloudfront
                # Content-Type: text/html
                # Date: Sat, 26 Oct 2019 01:01:21 GMT
                # Server: CloudFront
                # Via: 1.1 60858c13889b9be849ae025edc06577d.cloudfront.net (CloudFront)
                # X-Amz-Cf-Pop: ARN53
                # X-Cache: Error from cloudfront
                assert scores["blocking_general"] == 1.0

            elif rid == "20191026T001625Z_AS19108_G9uGTtyJCiOzeCm4jHsP6r8WRZ8cWx07wvcjwAVmrTshJ8WYwA":
                # requests: is empty
                assert scores["accuracy"] == 0

            elif debug:
                print("https://explorer.ooni.org/measurement/{}".format(rid))
                print_msm(msm)
                print(scores)
                assert 0


def test_score_psiphon(cans):
    for can_fn, msm in s3msmts("psiphon", date(2019, 12, 20), date(2020, 1, 10)):
        assert msm["test_name"] == "psiphon"
        rid = msm["report_id"]
        # test version 0.3.1 has different mkeys than before
        mkeys = set(msm.keys())
        mkeys.discard("resolver_ip")  # Some msmts are missing this
        assert len(mkeys) in (13, 15)
        assert len(msm["test_keys"]) in (3, 6, 7)
        assert 1 < msm["test_keys"]["bootstrap_time"] < 500
        assert msm["test_keys"]["failure"] is None, msm
        scores = fp.score_measurement(msm, [])
        if rid == "20200109T111813Z_AS30722_RZeO9Ix6ET2LJzqGcinrDp1iqrhaGGDCHSwlOoybq2N9kZITQt":
            assert scores == {
                "blocking_general": 0.0,
                "blocking_global": 0.0,
                "blocking_country": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
            }



def test_score_http_invalid_request_line_1():
    # https://github.com/ooni/pipeline/issues/294
    # https://explorer.ooni.org/measurement/20190411T192031Z_AS12353_JcA0e4AwUYYzR8aSXkoOiPGSiSmG8naeMOYnOPisECTr5bqelw
    # AdGuard
    fn = "fastpath/tests/data/mbx-1.json"
    with open(fn) as f:
        msm = ujson.load(f)
    matches = []
    scores = fp.score_measurement(msm, [])
    assert scores == {
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_score_http_invalid_request_line_2():
    # https://github.com/ooni/pipeline/issues/293
    # https://explorer.ooni.org/measurement/20181223T053541Z_AS37211_Vjr633mrbpd5UwOkZXid7U8QnwdDILnDu63UTFd1gE7zR4gnhN
    fn = "fastpath/tests/data/mbx-2.json"
    with open(fn) as f:
        msm = ujson.load(f)
    matches = []
    scores = fp.score_measurement(msm, [])
    assert scores == {
        "blocking_general": 1.0,
        "blocking_global": 0.0,
        "blocking_country": 0.0,
        "blocking_isp": 0.0,
        "blocking_local": 0.0,
    }


def test_score_http_invalid_request_line():
    optional = frozenset(
        (
            "backend_version",
            "bucket_date",
            "id",
            "input",
            "input_hashes",
            "options",
            "probe_city",
            "report_filename",
            "resolver_asn",
            "resolver_ip",
            "resolver_network_name",
            "test_helpers",
        )
    )
    always_present = frozenset(
        (
            "annotations",
            "data_format_version",
            "measurement_start_time",
            "probe_asn",
            "probe_cc",
            "probe_ip",
            "report_id",
            "software_name",
            "software_version",
            "test_keys",
            "test_name",
            "test_runtime",
            "test_start_time",
            "test_version",
        )
    )
    allkeys = optional | always_present
    for can_fn, msm in s3msmts("http_invalid_request_line", date(2019, 12, 3), date(2019, 12, 5)):
        assert msm["test_name"] == "http_invalid_request_line"
        for k in msm:
            assert k in allkeys
        for k in always_present:
            assert k in msm
        scores = fp.score_measurement(msm, [])
        rid = msm["report_id"]
        if rid == "20191203T020321Z_AS21502_wcb1ieBo7mO2vffn2FOlQW2oPw4QiaOoLiYGWoecyV5aQQaMGm":
            # failure
            assert scores["accuracy"] == 0.0
