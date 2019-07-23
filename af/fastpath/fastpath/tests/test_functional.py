"""
Simulate feeding from the collectors or cans on S3 using a local can
"""

# Silence pandas deprecation warnings
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

from contextlib import contextmanager
from datetime import date
from enum import Enum
from mock import patch
from pathlib import Path
import cProfile, pstats
import hashlib
import logging
import os
import time

import boto3  # debdeps: python3-boto3

import pytest  # debdeps: python3-pytest

import pandas as pd  # debdeps: python3-pandas python3-bottleneck python3-numexpr
import numpy as np
import matplotlib.pyplot as plt

from fastpath.fastpath import core
from fastpath.normalize import iter_yaml_lz4_reports
from fastpath.utils import fingerprints
import fastpath.fastpath as fp

log = logging.getLogger()


def fetch_cans_from_s3_if_needed():
    """
    Download interesting cans to a local directory

    Uses credentials from ~/.aws/config in the block:
    [ooni-data-private]
    aws_access_key_id = ...
    aws_secret_access_key = ...

    Explore bucket from CLI:
    AWS_PROFILE=ooni-data-private aws s3 ls s3://ooni-data-private/canned/2019-07-16/
    """

    fnames = (
        # "2013-05-05/20130505T065438Z-VN-AS24173-captive_portal-no_report_id-0.1.0-probe.yaml.lz4",
        "2018-05-07/20180501T071932Z-IT-AS198471-web_connectivity-20180506T090836Z_AS198471_gKqEpbg0Ny30ldGCQockbZMJSg9HhFiSizjey5e6JxSEHvzm7j-0.2.0-probe.json.lz4",
        "2013-09-12/20130912T150305Z-MD-AS1547-http_requests-no_report_id-0.1.0-probe.yaml.lz4",
        "2013-05-05/20130505T103213Z-VN-AS24173-http_requests-no_report_id-0.1.0-probe.yaml.lz4",
        "2018-05-07/20180501T071932Z-IT-AS198471-web_connectivity-20180506T090836Z_AS198471_gKqEpbg0Ny30ldGCQockbZMJSg9HhFiSizjey5e6JxSEHvzm7j-0.2.0-probe.json.lz4",
        "2018-05-07/20180506T014008Z-CN-AS4134-web_connectivity-20180506T014010Z_AS4134_ZpxhAVt3iqCjT5bW5CfJspbqUcfO4oZfzDVjCWAu2UuVkibFsv-0.2.0-probe.json.lz4",
    )
    # "2019-07-18/20190718T062527Z-http_header_field_manipulation-20190718T062527Z_AS131222_mBLc1XGcG2c0WuYOMFymz8TDzlLalzmtzIX3ADHpuxYWixm0Wa-AS131222-ZZ-probe-0.2.0.yaml",
    fnames = [os.path.join("testdata", fn) for fn in fnames]
    to_dload = sorted(fn for fn in fnames if not os.path.isfile(fn))
    # FIXME
    return fnames
    # FIXME: fetch_msm_dataframe download cans by itself
    if not to_dload:
        return fnames

    bname = "ooni-data-private"
    boto3.setup_default_session(profile_name="ooni-data-private")
    s3 = boto3.client("s3")
    for fn in to_dload:
        s3fname = fn.replace("testdata", "canned")
        r = s3.list_objects_v2(Bucket=bname, Prefix=s3fname)
        filedesc = r["Contents"][0]
        size = filedesc["Size"]
        print("Downloading can %s size %d MB" % (fn, size / 1024 / 1024))

        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, "wb") as f:
            s3.download_fileobj(bname, s3fname, f)
        assert size == os.path.getsize(fn)

    return fnames


@pytest.fixture
def cans():
    return fetch_cans_from_s3_if_needed()


# TODO mock out metrics


def notest_load_yaml_cans(cans):
    t0 = time.time()
    for can in cans:
        if "yaml" not in can:
            continue
        print("PROCESSING", can)
        cnt = 0
        for report in iter_yaml_lz4_reports(can):
            cnt += 1
            # r = report[3]
            # print(cnt, r.get('body_proportion', None))
    print("Load time", time.time() - t0)
    assert cnt == 327


def notest_load_yaml_can(cans):
    print("no mmap")
    can = "testdata/2013-09-12/20130912T150305Z-MD-AS1547-http_requests-no_report_id-0.1.0-probe.yaml.lz4"
    t0 = time.time()
    cnt = 0
    for report in iter_yaml_lz4_reports(can):
        cnt += 1
    print("Load time", time.time() - t0)
    assert cnt == 40875


def notest_core(cans):
    can = "testdata/2018-05-07/20180506T014008Z-CN-AS4134-web_connectivity-20180506T014010Z_AS4134_ZpxhAVt3iqCjT5bW5CfJspbqUcfO4oZfzDVjCWAu2UuVkibFsv-0.2.0-probe.json.lz4"
    core(can)


import json


def jsha(j):
    # deterministic hash to compare entries
    x = json.dumps(j, sort_keys=True)
    return hashlib.sha1(x.encode()).hexdigest()[:8]


def notest_normalize_json(cans):
    can = "testdata/2018-05-07/20180506T014008Z-CN-AS4134-web_connectivity-20180506T014010Z_AS4134_ZpxhAVt3iqCjT5bW5CfJspbqUcfO4oZfzDVjCWAu2UuVkibFsv-0.2.0-probe.json.lz4"
    j = load_json_from_disk(can)
    expected = {0: "977713ee", 1: "42ec375e", 2: "9bec4a5f", 3: "a38504ed"}
    for n, entry in enumerate(j):
        esha = b"x" * 20
        entry = normalize_entry(entry, "2018-05-07", "??", esha)
        if n in expected:
            assert jsha(entry) == expected[n]


def notest_normalize_yaml(cans):
    # data_format_version is not 0.2.0
    can = "testdata/2013-05-05/20130505T103213Z-VN-AS24173-http_requests-no_report_id-0.1.0-probe.yaml.lz4"
    for r in iter_yaml_lz4_reports(can):
        off, entry_len, esha, entry, exc = r
        entry = normalize_entry(entry, "2018-05-07", "??", esha)


def notest_normalize_yaml_sanitise_tcp_connect_bridge_reach(cans):
    # data_format_version is not 0.2.0
    pass


def notest_normalize_all(cans):
    for can in cans:
        print(can)
        t0 = time.time()
        if "json" in can:
            j = load_json_from_disk(can)
            continue  # TODO
            for entry in j:
                esha = b"x" * 20
                normalize_entry(entry, "2018-05-07", "??", esha)
        else:
            for r in iter_yaml_lz4_reports(can):
                off, entry_len, esha, entry, exc = r
                normalize_entry(entry, "2018-05-07", "??", esha)
        print(time.time() - t0)


from fastpath.normalize import gen_simhash


def test_simhash():
    s = "".join(str(x) for x in range(1000))
    assert gen_simhash("") == 16_825_458_760_271_544_958
    assert gen_simhash("hello") == 36_330_143_249_342_482
    assert gen_simhash(s) == 816_031_085_364_464_265


def profile_simhash():
    import cProfile

    pr = cProfile.Profile()
    pr.enable()
    for x in range(40000):
        gen_simhash(str(x))
    pr.disable()
    pr.print_stats(sort=1)


def setup_module(module):
    fp.conf.devel = True
    fp.conf.interact = False
    fp.conf.vardir = Path("var/lib/fastpath")
    fp.conf.cachedir = fp.conf.vardir / "cache"
    fp.conf.s3cachedir = fp.conf.cachedir / "s3"
    fp.conf.sshcachedir = fp.conf.cachedir / "ssh"


## Test process_measurements ##

mock_fingerprints = [
    {"header_name": "Age", "header_full": "333"},
    {"header_name": "Last-Modified", "header_full": "Wed, 17 Jul 2019 11:54:36 GMT"},
]


@contextmanager
def profile():
    pr = cProfile.Profile()
    pr.enable()
    yield
    pr.disable()
    ps = pstats.Stats(pr).sort_stats(pstats.SortKey.CUMULATIVE)
    ps.print_stats(20)


@patch.dict(fingerprints, {"US": mock_fingerprints}, clear=True)
def test_process_measurements():
    with open("tests/data/report1.json") as f:
        r1 = json.load(f)
    with open("tests/data/report1blocked.json") as f:
        r1blk = json.load(f)
    with open("tests/data/report2.json") as f:
        r2 = json.load(f)

    msm = pd.DataFrame([r1, r1blk])
    agg = fp.Cuboids(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    out = fp.process_measurements(msm, agg)
    assert sum(out.fingerprint_matched == True) == 1
    assert agg.day_target_cc_msmcnt_blockedcnt.shape[0] == 1
    assert agg.day_target_cc_msmcnt_blockedcnt.reset_index().ratio[0] == 0.5

    # add another r1
    msm = pd.DataFrame([r1])
    out = fp.process_measurements(msm, agg)
    print(repr(agg.day_target_cc_msmcnt_blockedcnt))
    assert agg.day_target_cc_msmcnt_blockedcnt.shape[0] == 1
    assert agg.day_target_cc_msmcnt_blockedcnt.reset_index().cnt[False][0] == 2

    msm = pd.DataFrame([r2])
    out = fp.process_measurements(msm, agg)
    assert sum(out.fingerprint_matched == True) == 0
    assert agg.day_target_cc_msmcnt_blockedcnt.shape[0] == 8
    log.info(agg.day_target_cc_msmcnt_blockedcnt)


def test_windowing():
    ## Generates tests/output/blocking_detection.png
    # Create a reproducible set of measurement_start_time and blocking_general
    fig, ax = plt.subplots()
    np.random.seed(0)
    n = 100
    start_t = 1_565_000_000
    end_t = start_t + (3600 * 24 * 14)
    e = sorted(10 ** 9 * np.random.randint(start_t, end_t, n))
    d = {
        "blocking_general": np.random.random(n) * 0.8
        + np.sin(np.arange(n) / n * 14) / 2,
        "measurement_start_time": pd.to_datetime(e),
    }
    df = pd.DataFrame(d, index=pd.DatetimeIndex(e))
    df.blocking_general = df.blocking_general.clip(0, 1)
    df.blocking_general.plot(ax=ax)

    blk = fp.detect_blocking_changes(df)
    assert blk.shape[0] == 4

    blk.loc[:, "blocked_n"] = blk.blocked.astype(int)
    blk.plot(
        x="measurement_start_time", y="blocked_n", style="o", ax=ax
    ).get_figure().savefig("tests/output/blocking_detection.png")


@pytest.fixture
def mockmsm():
    # Generate mock msm with blocking_general going up and down
    n = 50
    timespan_hours = 48
    np.random.seed(0)
    start_t = 1_565_000_000
    end_t = start_t + (3600 * timespan_hours)
    dates = pd.to_datetime(sorted(10 ** 9 * np.random.randint(start_t, end_t, n)))
    bg = np.random.random(n) * 0.8 + np.cos(np.arange(n) / n * 19) / 2
    bg = bg.clip(0, 1)
    df = pd.DataFrame(
        dict(
            measurement_start_time=dates,
            cc=np.random.choice(["US", "RU"], n),
            test_name=np.random.choice(["web_connectivity"], n),
            input=np.random.choice(["foo", "bar"], n),
            blocking_general=bg,
        )
    )
    return df


def show(desc, item):
    log.info(desc + "\n" + repr(item))


def plot_blocking(msm, ewm, blk, cc, inp):
    # filter
    blk = blk.xs(cc, level="cc").xs(inp, level="input")
    msm = msm.xs(cc, level="cc").xs(inp, level="input")
    ewm = ewm.xs(cc, level="cc").xs(inp, level="input")

    fn = f"tests/output/blocking_detection_{cc}_{inp}.png"
    fig, ax = plt.subplots()

    # plot blocking_general value
    msm.plot(x="measurement_start_time", y="blocking_general", ax=ax)

    # plot blocking_general EWM value
    ewm.plot(x="measurement_start_time", y="blocking_general", ax=ax)

    # plot detected events
    blk.blocked = blk.blocked.astype(int)
    blk.plot(
        x="measurement_start_time", y="blocked", style="o", ax=ax
    ).get_figure().savefig(fn)


def test_windowing_mock_msm(mockmsm):
    mockmsm.set_index(["cc", "test_name", "input"], inplace=True)
    blk = mockmsm.groupby(level=["cc", "test_name", "input"]).apply(
        lambda df: fp.detect_blocking_changes_f(df)
    )

    # redo generate_ewm: it's not exposed by detect_blocking_changes_f
    ewm = mockmsm.groupby(level=["cc", "test_name", "input"]).apply(
        lambda x: fp.generate_ewm(x)
    )
    for cc in ("US", "RU"):
        for inp in ("bar",):
            # plot one cc/input to tests/output/blocking_detection_...
            plot_blocking(mockmsm, ewm, blk, cc, inp)


@pytest.fixture
def baked_scores():
    ## Prepare and cache a scores dataframe
    if not os.path.isfile("scores.mpk"):
        log.info("Caching scores dataframe")
        t = time.time()
        gen = fp.fetch_msm_dataframe(
            date(2019, 7, 21), date(2019, 7, 22), blocksize=100 * 1000
        )
        # blocksize=1000)
        # blocksize=100 * 1000)
        msm = next(gen)
        log.info("Loading done in %r s", time.time() - t)

        # Msgpack: 536M saved in 11s and loaded in 2.8s   (8528 measurements)
        # Loading the same df from cans takes 10.1s (!)

        # t = time.time()
        # msm.to_msgpack("msm.mpk")
        # log.info("save msm mpk %r", time.time() - t)
        # t = time.time()
        # pd.read_msgpack("msm.mpk")
        # log.info("load msm mpk %r", time.time() - t)

        aggregation_cuboids = fp.load_aggregation_cuboids()
        scores = fp.process_measurements(msm, aggregation_cuboids)
        scores.to_msgpack("scores.mpk")

    return pd.read_msgpack("scores.mpk")


def test_windowing_on_real_data(baked_scores):
    ## Generates tests/output/blocking_detection.png
    scores = baked_scores
    assert len(baked_scores.index) > 0
    status = {}
    means = {}
    fp.detect_blocking_changes_on_msm(scores, status, means)
    log.info("Msm size: %d", len(baked_scores.index))
    log.info("Status size: %d", len(status))
    for (cc, test_name, inp), blocked in status.items():
        if blocked == 0:
            continue
        s = "detected" if blocked > 1 else "cleared"
        log.info("Blocking %s %s %s %s", s, cc, test_name, inp)


def test_windowing_new():
    ## Generates tests/output/blocking_detection.png
    scores = pd.DataFrame(
        data=dict(
            blocking_general=[0.0, 0.9],
            cc=["CA", "UK"],
            measurement_start_time=[3, 4],
            test_name=["web_connectivity", "web_connectivity"],
            input=["foo", "bar"],
        )
    )
    # scores.set_index(["measurement_start_time"], inplace=True)
    status = {}
    means = {}
    fp.detect_blocking_changes_on_msm(scores, status, means)
    assert status == {
        ("CA", "web_connectivity", "foo"): 0,
        ("UK", "web_connectivity", "bar"): 3,
    }
    status = fp.reset_status(status)
    assert status == {("UK", "web_connectivity", "bar"): 1}

    scores[scores.cc == "CA"].global_blocking = 1.0
    scores[scores.cc == "UK"].global_blocking = 0.1

    fp.detect_blocking_changes_on_msm(scores, status, means)
    status = fp.reset_status(status)
    fp.detect_blocking_changes_on_msm(scores, status, means)
    log.info(status)
    assert status == {
        ("UK", "web_connectivity", "bar"): 1,
        ("CA", "web_connectivity", "foo"): 0,
    }
    # for (cc, test_name, inp), blocked in status.items():
    #     if blocked == 0:
    #         continue
    #     s = "detected" if blocked > 1 else "cleared"
    #     log.info("Blocking %s %s %s %s", s, cc, test_name, inp)


def notest_process_measurements_real_files():
    rg = fp.load_s3_reports("2019-07-21")
    msm = pd.DataFrame(list(rg))
    msm = fp.process_measurements(msm)
    assert msm.shape[0] == 1219
