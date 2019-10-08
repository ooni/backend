"""
Simulate feeding from the collectors or cans on S3 using a local can
"""

# Silence pandas deprecation warnings
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

from contextlib import contextmanager
from datetime import date
from pathlib import Path
import cProfile, pstats
import hashlib
import logging
import os
import time

import ujson
import boto3  # debdeps: python3-boto3
import pytest  # debdeps: python3-pytest

import fastpath.core as fp
import fastpath.normalize as norm
from fastpath.normalize import gen_simhash
from fastpath.normalize import iter_yaml_lz4_reports, normalize_entry

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
        # "2013-05-05/20130505T065438Z-VN-AS24173-captive_portal-no_report_id-0.1.0-probe.yaml.lz4",
        # "2013-09-12/20130912T150305Z-MD-AS1547-http_requests-no_report_id-0.1.0-probe.yaml.lz4",
        vn = "2013-05-05/20130505T103213Z-VN-AS24173-http_requests-no_report_id-0.1.0-probe.yaml.lz4",
        it = "2018-05-07/20180501T071932Z-IT-AS198471-web_connectivity-20180506T090836Z_AS198471_gKqEpbg0Ny30ldGCQockbZMJSg9HhFiSizjey5e6JxSEHvzm7j-0.2.0-probe.json.lz4",
        cn = "2018-05-07/20180506T014008Z-CN-AS4134-web_connectivity-20180506T014010Z_AS4134_ZpxhAVt3iqCjT5bW5CfJspbqUcfO4oZfzDVjCWAu2UuVkibFsv-0.2.0-probe.json.lz4",
        yaml16 = "2016-07-07/20160706T000046Z-GB-AS9105-http_requests-TYXZLcFg4yUp9Io2LrOMM7CjLk0QcIdsMPiCZtVgkxUrTxnFM0GiMbr8iGDl3OEe-0.1.0-probe.yaml.lz4",
        yaml17 = "2017-12-21/20171220T153044Z-BE-AS5432-dns_consistency-mnKRlHuqk8Eo6XMJt5ZkVQrgReaEXPEWaO9NafgXxSVIhAswTXT7QJc6zhsuttpK-0.1.0-probe.yaml.lz4",
        yaml18 = "2018-03-21/20180320T211810Z-NL-AS1103-dns_consistency-yiCRUmXy6MndqnV3g5QYBKGich5OwP9cQQfOiYnxYAfZatgQZlStuWIT30yu586R-0.1.0-probe.yaml.lz4",
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
    # can = "testdata/2013-09-12/20130912T150305Z-MD-AS1547-http_requests-no_report_id-0.1.0-probe.yaml.lz4"
    fn = "fastpath/tests/data/20190912T115043Z-ndt7-20190912T115043Z_AS15169_0B9KifXvlmX0yttm3Q5rfUL9YYed8uXrvRtPELmZuuFek7NJDf-AS15169-US-probe-0.2.0.yaml"

    t0 = time.time()
    cnt = 0
    for report in iter_yaml_lz4_reports(can):
        cnt += 1
    print("Load time", time.time() - t0)
    assert cnt == 40875


def notest_core(cans):
    can = "testdata/2018-05-07/20180506T014008Z-CN-AS4134-web_connectivity-20180506T014010Z_AS4134_ZpxhAVt3iqCjT5bW5CfJspbqUcfO4oZfzDVjCWAu2UuVkibFsv-0.2.0-probe.json.lz4"
    core(can)




def load_json_from_disk(fn):
    with open(fn) as f:
        return ujson.load(f)


def hash(j):
    # deterministic hash to compare entries
    jstr = ujson.dumps(j, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.shake_128(jstr).hexdigest(4)


def notest_normalize_json(cans):
    # can = "testdata/2018-05-07/20180506T014008Z-CN-AS4134-web_connectivity-20180506T014010Z_AS4134_ZpxhAVt3iqCjT5bW5CfJspbqUcfO4oZfzDVjCWAu2UuVkibFsv-0.2.0-probe.json.lz4"
    j = load_json_from_disk(fn)
    expected = {0: "977713ee", 1: "42ec375e", 2: "9bec4a5f", 3: "a38504ed"}
    for n, entry in enumerate(j):
        esha = b"x" * 20
        entry = normalize_entry(entry, "2018-05-07", "??", esha)
        if n in expected:
            assert hash(entry) == expected[n]


# def test_normalize_yaml(cans):
#    # data_format_version is not 0.2.0
#    can = "testdata/2013-05-05/20130505T103213Z-VN-AS24173-http_requests-no_report_id-0.1.0-probe.yaml.lz4"
#    #fn = "fastpath/tests/data/20190912T115043Z-ndt7-20190912T115043Z_AS15169_0B9KifXvlmX0yttm3Q5rfUL9YYed8uXrvRtPELmZuuFek7NJDf-AS15169-US-probe-0.2.0.yaml"
#    for r in iter_yaml_lz4_reports(can):
#        off, entry_len, esha, entry, exc = r
#        entry = normalize_entry(entry, "2018-05-07", "??", esha)


## YAML normalization

def FIXME_test_normalize_yaml_2016(cans):
    can = "fastpath/tests/data/20160706T000046Z-GB-AS9105-http_requests-TYXZLcFg4yUp9Io2LrOMM7CjLk0QcIdsMPiCZtVgkxUrTxnFM0GiMbr8iGDl3OEe-0.1.0-probe.yaml.lz4"
    tested_categories = set(
        (
            "captive_portal",
            "chinatrigger",
            "dns_consistency",
            "dns_injection",
            "dns_spoof",
            "domclass_collector",
            "http_filtering_bypass",
            "http_header_field_manipulation",
            "http_host",
            "http_invalid_request_line",
            "http_keyword_filtering",
            "http_requests",
            "http_trix",
            "http_uk_mobile_networks",
            "http_url_list",
            "keyword_filtering",
            "lantern",
            "meek_fronted_requests",
            "multi_protocol_traceroute",
            "parasitic_traceroute",
            "psiphon",
            "squid",
            "tor_http_requests_test",
        )
    )
    for n, r in enumerate(iter_yaml_lz4_reports(can)):
        off, entry_len, esha, entry, exc = r
        print(entry["test_name"])
        test_name = entry.get("test_name", "invalid")
        test_name = norm.test_name_mappings.get(test_name, test_name.lower())
        if test_name not in tested_categories:
            continue
        print(test_name)
        print("****")
        print(n)

        tested_categories.discard(test_name)

        entry = norm.normalize_entry(entry, "2018-05-07", "??", esha)
        assert hash(entry) == "e83a742b"

        if len(tested_categories) < 20:
            print("done break %d" % n)
            break  # we are done

    print("done %d", n)
    print(tested_categories)


def test_normalize_yaml_2016(cans):
    can = cans["yaml16"]
    for n, r in enumerate(iter_yaml_lz4_reports(can)):
        off, entry_len, esha, entry, exc = r
        entry = norm.normalize_entry(entry, "2018-05-07", "??", esha)
        assert hash(entry) == "e83a742b"
        break


def test_normalize_yaml_dns_consistency_2017(cans):
    can = cans["yaml17"]
    for n, r in enumerate(iter_yaml_lz4_reports(can)):
        off, entry_len, esha, entry, exc = r
        entry = norm.normalize_entry(entry, "2018-05-07", "??", esha)
        assert hash(entry) == "685b9af4"
        break


def test_normalize_yaml_dns_consistency_2018(cans):
    can = cans["yaml18"]
    for n, r in enumerate(iter_yaml_lz4_reports(can)):
        off, entry_len, esha, entry, exc = r
        entry = norm.normalize_entry(entry, "2018-05-07", "??", esha)
        assert hash(entry) == "c9d0b754"
        break


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




def test_simhash():
    s = "".join(str(x) for x in range(1000))
    assert gen_simhash("") == 16_825_458_760_271_544_958
    assert gen_simhash("hello") == 36_330_143_249_342_482
    assert gen_simhash(s) == 816_031_085_364_464_265


def benchmark_simhash(benchmark):
    # debdeps: python3-pytest-benchmark
    for x in range(400):
        gen_simhash(str(x))


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


# @patch.dict(fingerprints, {"US": mock_fingerprints}, clear=True)


# def test_windowing():
#     ## Generates tests/output/blocking_detection.png
#     # Create a reproducible set of measurement_start_time and blocking_general
#     fig, ax = plt.subplots()
#     np.random.seed(0)
#     n = 100
#     start_t = 1_565_000_000
#     end_t = start_t + (3600 * 24 * 14)
#     e = sorted(10 ** 9 * np.random.randint(start_t, end_t, n))
#     d = {
#         "blocking_general": np.random.random(n) * 0.8
#         + np.sin(np.arange(n) / n * 14) / 2,
#         "measurement_start_time": pd.to_datetime(e),
#     }
#     df = pd.DataFrame(d, index=pd.DatetimeIndex(e))
#     df.blocking_general = df.blocking_general.clip(0, 1)
#     df.blocking_general.plot(ax=ax)
#
#     blk = fp.detect_blocking_changes(df)
#     assert blk.shape[0] == 4
#
#     blk.loc[:, "blocked_n"] = blk.blocked.astype(int)
#     blk.plot(
#         x="measurement_start_time", y="blocked_n", style="o", ax=ax
#     ).get_figure().savefig("tests/output/blocking_detection.png")


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


# def test_windowing_mock_msm(mockmsm):
#     mockmsm.set_index(["cc", "test_name", "input"], inplace=True)
#     blk = mockmsm.groupby(level=["cc", "test_name", "input"]).apply(
#         lambda df: fp.detect_blocking_changes_f(df)
#     )
#
#     # redo generate_ewm: it's not exposed by detect_blocking_changes_f
#     ewm = mockmsm.groupby(level=["cc", "test_name", "input"]).apply(
#         lambda x: fp.generate_ewm(x)
#     )
#     for cc in ("US", "RU"):
#         for inp in ("bar",):
#             # plot one cc/input to tests/output/blocking_detection_...
#             plot_blocking(mockmsm, ewm, blk, cc, inp)


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


def notest_process_measurements_real_files():
    rg = fp.load_s3_reports("2019-07-21")
    msm = pd.DataFrame(list(rg))
    msm = fp.process_measurements(msm)
    assert msm.shape[0] == 1219
