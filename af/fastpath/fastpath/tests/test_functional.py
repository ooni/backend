"""
Simulate feeding from the collectors or cans on S3 using a local can
"""
# Format with black -t py37 -l 120

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
        it="2018-05-07/20180501T071932Z-IT-AS198471-web_connectivity-20180506T090836Z_AS198471_gKqEpbg0Ny30ldGCQockbZMJSg9HhFiSizjey5e6JxSEHvzm7j-0.2.0-probe.json.lz4",
        cn="2018-05-07/20180506T014008Z-CN-AS4134-web_connectivity-20180506T014010Z_AS4134_ZpxhAVt3iqCjT5bW5CfJspbqUcfO4oZfzDVjCWAu2UuVkibFsv-0.2.0-probe.json.lz4",
        telegram="2019-08-29/telegram.0.tar.lz4",
        whatsapp="2019-08-29/whatsapp.0.tar.lz4",
        # telegram="2019-08-29/20190829T105210Z-IR-AS31549-telegram-20190829T105214Z_AS31549_t32ZZ5av3B6yNruRIFhCnuT1dHTnwPk7vwIa9F0TAe064HG4tk-0.2.0-probe.json",
        # whatsapp="2019-06-15/20190615T070248Z-ET-AS24757-whatsapp-20190615T070253Z_AS24757_gRi6dhAqgWa7Yp4tah4LX6Rl1j6c8kJuja3OgZranEpMicEj2p-0.2.0-probe.json",
        # fb="2019-06-27/20190627T214121Z-ET-AS24757-facebook_messenger-20190627T214126Z_AS24757_h8g9P5kTmmzyX1VyOjqcVonIbFNujm84l2leMCwC2gX3BI78fI-0.2.0-probe.json",
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
            elif isinstance(v, list) or isinstance(v, dict):
                print("{}{}:".format(ind, k))
                _print_msm_node(n[k], depth + 1)
            else:
                print("{}{}: {}".format(ind, k, v))

    else:
        print(ind, n)


print_msm = _print_msm_node


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
    for measurement_tup in s3feeder.load_multiple(can.as_posix()):
        msm_jstr, msm = measurement_tup
        if msm is None:
            msm = ujson.loads(msm_jstr)
        summary = fp.score_measurement(msm, [])
        if msm["report_id"] == "20190830T002837Z_AS209_3nMvNkLIqSZMLqRiaiQylAuHxu6qpK7rVJcAA9Dv2UpcNMhPH0":
            assert summary["scores"] == {
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
            assert summary["scores"] == {
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
            assert summary["scores"] == {
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
            assert summary["scores"] == {
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
    for measurement_tup in s3feeder.load_multiple(can.as_posix()):
        msm_jstr, msm = measurement_tup
        msm = msm or ujson.loads(msm_jstr)
        summary = fp.score_measurement(msm, [])
        # fmt: off
        if msm["report_id"] == "20190830T002828Z_AS209_fDHPMTveZ66kGmktmW8JiGDgqAJRivgmBkZjAVRmFbH92OIlTX":
            assert summary["scores"] == {
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
            assert summary["scores"] == {
                "blocking_general": 0.0,
                "blocking_global": 0.0,
                "blocking_country": 0.0,
                "blocking_isp": 0.0,
                "blocking_local": 0.0,
            }, msm

        # To inspect the test dataset for false positives run this:
        if debug and summary["scores"]["blocking_general"] > 0:
            print("-----")
            print_msm(msm)
            print(summary["scores"])
            raise Exception("debug")
