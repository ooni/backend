"""
Simulate feeding from the collectors or cans on S3 using a local can
"""
# Format with black -t py37 -l 120

from collections import Counter
from pathlib import Path
import logging
import os

import ujson
import boto3  # debdeps: python3-boto3
import pytest  # debdeps: python3-pytest

import fastpath.core as fp
import fastpath.s3feeder as s3feeder

# from fastpath.utils import fingerprints

log = logging.getLogger()


@pytest.fixture
def cans():
    """
    Download interesting cans from S3 to a local directory

    Uses credentials from ~/.aws/config in the block:
    [ooni-data-private]
    aws_access_key_id = ...
    aws_secret_access_key = ...

    Explore bucket from CLI:
    AWS_PROFILE=ooni-data-private aws s3 ls s3://ooni-data-private/canned/2019-07-16/
    """
    _cans = dict(
        web_conn_it="2018-05-07/20180501T071932Z-IT-AS198471-web_connectivity-20180506T090836Z_AS198471_gKqEpbg0Ny30ldGCQockbZMJSg9HhFiSizjey5e6JxSEHvzm7j-0.2.0-probe.json.lz4",
        web_conn_cn="2018-05-07/20180506T014008Z-CN-AS4134-web_connectivity-20180506T014010Z_AS4134_ZpxhAVt3iqCjT5bW5CfJspbqUcfO4oZfzDVjCWAu2UuVkibFsv-0.2.0-probe.json.lz4",
        web_conn_30="2019-10-30/web_connectivity.00.tar.lz4",
        telegram="2019-08-29/telegram.0.tar.lz4",
        whatsapp="2019-08-29/whatsapp.0.tar.lz4",
        facebook_messenger="2019-08-29/facebook_messenger.0.tar.lz4",
        facebook_messenger2="2019-10-29/facebook_messenger.0.tar.lz4",
        # telegram="2019-08-29/20190829T105210Z-IR-AS31549-telegram-20190829T105214Z_AS31549_t32ZZ5av3B6yNruRIFhCnuT1dHTnwPk7vwIa9F0TAe064HG4tk-0.2.0-probe.json",
        # whatsapp="2019-06-15/20190615T070248Z-ET-AS24757-whatsapp-20190615T070253Z_AS24757_gRi6dhAqgWa7Yp4tah4LX6Rl1j6c8kJuja3OgZranEpMicEj2p-0.2.0-probe.json",
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
        hirl_2019_10_26="2019-10-26/http_invalid_request_line.0.tar.lz4",
    )
    for k, v in _cans.items():
        _cans[k] = Path("testdata") / v

    to_dload = sorted(f for f in _cans.values() if not f.is_file())
    if not to_dload:
        return _cans

    bname = "ooni-data-private"
    boto3.setup_default_session(profile_name="ooni-data-private")
    s3 = boto3.client("s3")
    for fn in to_dload:
        s3fname = fn.as_posix().replace("testdata", "canned")
        r = s3.list_objects_v2(Bucket=bname, Prefix=s3fname)
        assert r["KeyCount"] == 1, r
        filedesc = r["Contents"][0]
        size = filedesc["Size"]
        print("Downloading can %s size %d MB" % (fn, size / 1024 / 1024))

        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, "wb") as f:
            s3.download_fileobj(bname, s3fname, f)
        assert size == os.path.getsize(fn)

    return _cans


def list_cans_on_s3_for_a_day(day, filter=None):
    s3 = s3feeder.create_s3_client()
    fns = s3feeder.list_cans_on_s3_for_a_day(s3, day)
    for fn, size in sorted(fns):
        if filter is None or (filter in fn):
            print(fn, size)


def disabled_test_list_cans():
    """Used for debugging"""
    f = "psiphon"
    for d in range(26, 31):
        list_cans_on_s3_for_a_day("2019-10-{}".format(d), filter=f)
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
            #elif k == "tor_log":
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
    for msm_jstr, msm in s3feeder.load_multiple(can.as_posix(), touch=False):
        msm = msm or ujson.loads(msm_jstr)
        if msm.get("report_id", None) is None:
            # Missing or empty report_id
            # https://github.com/ooni/probe-engine/pull/104
            continue
        yield msm


# TODO mock out metrics


def setup_module(module):
    fp.conf.devel = True
    fp.conf.interact = False
    fp.conf.vardir = Path("var/lib/fastpath")
    fp.conf.cachedir = fp.conf.vardir / "cache"
    fp.conf.s3cachedir = fp.conf.cachedir / "s3"
    fp.conf.sshcachedir = fp.conf.cachedir / "ssh"


def test_telegram(cans):
    can = cans["telegram"]
    for msm in load_can(can):
        scores = fp.score_measurement(msm, [])
        if msm["report_id"] == "20190830T002837Z_AS209_3nMvNkLIqSZMLqRiaiQylAuHxu6qpK7rVJcAA9Dv2UpcNMhPH0":
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

        elif msm["report_id"] == "20190829T205910Z_AS45184_0TVMQZLWjkfOdqA5b5nNF1XHrafTD4H01GnVTwvfzfiLyLc45r":
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
        elif msm["report_id"] == "20190829T210302Z_AS197207_28cN0a47WSIxF3SZlXvceoLCSk3rSkyeg0n07pKGAi7XYyEQXM":
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
        elif msm["report_id"] == "20190829T220118Z_AS16345_28eP4Hw7PQsLmb4eEPWitNvIZH8utHddaTbWZ9qFcaZudmHPfz":
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
    for msm in load_can(can):
        scores = fp.score_measurement(msm, [])
        if msm["report_id"] == "20190830T002828Z_AS209_fDHPMTveZ66kGmktmW8JiGDgqAJRivgmBkZjAVRmFbH92OIlTX":
            assert scores == {
                "blocking_general": 0.8,
                "blocking_global": 0.0,
                "blocking_country": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
            }, msm

        if msm["report_id"] == "20190829T002541Z_AS29119_kyaEYabRxQW6q41n4kPH9aX5cvFEXNheCj1fguSf4js3JydUbr":
            # The probe is reporting a false positive: due to the empty client headers
            # it hits https://www.whatsapp.com/unsupportedbrowser
            print_msm(msm)
            assert scores == {
                "blocking_general": 0.0,
                "blocking_global": 0.0,
                "blocking_country": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
            }, msm

        # To inspect the test dataset for false positives run this:
        if debug and scores["blocking_general"] > 0:
            print_msm(msm)
            print(scores)
            raise Exception("debug")


def test_facebook_messenger(cans):
    can = cans["facebook_messenger"]
    debug = False
    for msm in load_can(can):
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
    for msm in load_can(can):
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
    for tot, msm in enumerate(load_can(can)):
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
                print(msm["probe_cc"], msm["software_name"], msm["software_version"])
                print_msm(msm)
                print(scores)

    ratio = blocked_cnt / (tot + 1) * 100
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
        for msm in load_can(can):
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
                print(msm["test_start_time"], msm["probe_cc"], url, msm["test_keys"]["requests"][0].get("failure", None))
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
        print(
            msm["probe_cc"],
            msm["test_keys"]["requests"][0].get("failure", None),
        )

        d.update(("{}:{}".format(cc, fm),))
        s.update((fm,))

    #for i, c in d.most_common(120):
    #    print(i, c)
    for i, c in s.most_common(120):
        print(i, c)
    print("Total", sum(s.values()))
    assert 0


def test_score_vanilla_tor_2018(cans):
    can = cans["tor_2018_10_26"]
    timeouts = (
        "20181026T003600Z_AS4134_SIts9rD3mrpgIrxrBy6NY7LHJGsBm2dbV4Q8rOHnFEQVESMqB1",
        "20181026T154843Z_AS57963_GKCdB85BgIqr5frZ2Z8qOXVZgdpNGajLRXSidMeRVWg8Qvto3e",
    )
    for msm in load_can(can):
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
        for msm in load_can(can):
            scores = fp.score_measurement(msm, [])
            rid = msm["report_id"]
            cnt += 1
            if rid == "20191029T012425Z_AS45194_So00Y296Ve6q1TvjOtKqsvH1ieiVF566PlcUUOw4Ia37HGPwPL":
                # timeout
                assert scores["blocking_general"] > 0
                blocked_cnt +=1
                total_score += scores["blocking_general"]

            elif scores["blocking_general"] > 0:
                blocked_cnt +=1
                total_score += scores["blocking_general"]
                #print("https://explorer.ooni.org/measurement/{}".format(rid))
                #print_msm(msm)
                #print(scores)
                #assert 0

    p = blocked_cnt * 100 / cnt
    assert 0.35 < p < 0.36, p
    avg = total_score / cnt
    assert 0.003 < avg < 0.004


def test_score_web_connectivity(cans):
    # TODO: more thorough testing
    debug = 0
    can = cans["web_conn_30"]
    blocked = (
        "20191029T180431Z_AS50289_5IKNXzKJUvzKQqnlzU5r91F9KiCl1LfRlEBllZVbDHcDQg5TEt",
        "20191029T180509Z_AS50289_CqU5a3scgi1JJ8cWEYEMSqLUzseS0uIbnWcnGSKKlW1BMbnLc5",
    )
    nonblocked = (
        "20191029T180447Z_AS50289_yWeX5dJzPeh9Pk3TddqG2eO3BvLGT2SOWmOK0lhR7aRV0XX1RC",
        "20191029T180452Z_AS50289_IIuYcQRCGA9S2cj5zFABEOvMbyXSKBExWywVgZkpe5l1uAqyT5",
        "20191029T180525Z_AS50289_UfjRU99n2edoDn9PeWnqyGxHVorOAxBFwZj3WPQ24sl2ii4gC2",
    )
    for msm in load_can(can):
        scores = fp.score_measurement(msm, [])
        rid = msm["report_id"]
        bl = sum(scores[k] for k in scores if k.startswith("blocking_"))
        if rid in blocked:
            assert bl > 0

        elif rid in nonblocked:
            assert bl < 0.3

        elif debug and bl > 0:
            print("https://explorer.ooni.org/measurement/{}".format(rid))
            print_msm(msm)
            print(scores)
            assert 0


def test_score_ndt(cans):
    debug = 0
    can = cans["ndt_2018_10_26"]
    for msm in load_can(can):
        scores = fp.score_measurement(msm, [])
        assert scores == {}  # no scoring yet


def test_score_tcp_connect(cans):
    # tcp_connect msmts are identified by (report_id / input)
    debug = 0
    can = cans["tcp_connect_2018_10_26"]
    for msm in load_can(can):
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
        "20191026T015105Z_AS4837_7vwBtbVmZZqwZhdTHnqHan0Nwa7bi7TeJ789htG3RB91C3eyU1":
        (0.1, 0.0, "blocking_general"),
        "20191026T022317Z_AS17380_ZJGnXdvHl4j1M4xTeskrGhC8SW1KT4buJEjxCsTagCGO2NZeAD":
        (0.1, 0.0, "json_parse_error"),
        "20191026T032159Z_AS20057_xLjBSrTyZjOn6C7pa5BPyUxyBhzWHbSooKQjUY9zcWADnkakIR":
        (0.1, 0.0, "eof_error"),
        "20191026T051350Z_AS44244_9yjPG1UbgIjtAFg9LiTUxVhq7hGuG3tG4yMnvt6gRJTaFdQme6":
        (0.1, 0.0, "json_processing_error"),
        "20191026T071332Z_AS7713_caK9GNyp9ZhN7zL9cg2dg0zGhs44CwHmxZtOyK7B6rBKRaGGMF":
        (0.1, 0.0, "http_request_failed"),
        "20191026T093003Z_AS4837_yHZ0f8Oxyhus9vBKAUa0tA2XMSObIO0frShG6YBieBzY9RiSBg":
        (0.1, 0.0, "connect_error"),
        "20191026T165434Z_AS0_qPbZHZF8VXUWgzlvqT9Jd7ARuHSl2Dq4tPcEq580rgYZGmV5Um":
        (0.1, 0.0, "generic_timeout_error"),
        "20191028T160112Z_AS1640_f4zyjjp5vFcwZkAKPrTokayPRdcXPfdEMRbdo1LmIaLZRile6P":
        (0.1, 0.0, "broken_pipe"),
        "20191029T094043Z_AS49048_qGQxBh6lv26TOfuWfhGcUtz2LZWwboXlfbh058CSF1fOmEUv6Z":
        (0.1, 0.0, "connection_refused"),
    }
    for d in range(26, 30):
        can = cans["dash_2019_10_{}".format(d)]
        for msm in load_can(can):
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
