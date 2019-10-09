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
        entry = norm.normalize_entry(entry, "2018-05-07", "??", esha)
        if n in expected:
            assert hash(entry) == expected[n]


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
    for n, r in enumerate(norm.iter_yaml_lz4_reports(can)):
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
    for n, r in enumerate(norm.iter_yaml_lz4_reports(can)):
        off, entry_len, esha, entry, exc = r
        entry = norm.normalize_entry(entry, "2018-05-07", "??", esha)
        assert hash(entry) == "e83a742b"
        break


def test_normalize_yaml_dns_consistency_2017(cans):
    can = cans["yaml17"]
    for n, r in enumerate(norm.iter_yaml_lz4_reports(can)):
        off, entry_len, esha, entry, exc = r
        entry = norm.normalize_entry(entry, "2018-05-07", "??", esha)
        assert hash(entry) == "685b9af4"
        break


def test_normalize_yaml_dns_consistency_2018(cans):
    can = cans["yaml18"]
    for n, r in enumerate(norm.iter_yaml_lz4_reports(can)):
        off, entry_len, esha, entry, exc = r
        entry = norm.normalize_entry(entry, "2018-05-07", "??", esha)
        assert hash(entry) == "c9d0b754"
        break


def notest_normalize_all(cans):
    for can in cans:
        print(can)
        t0 = time.time()
        if "json" in can:
            j = load_json_from_disk(can)
            continue  # TODO
            for entry in j:
                esha = b"x" * 20
                norm.normalize_entry(entry, "2018-05-07", "??", esha)
        else:
            for r in iter_yaml_lz4_reports(can):
                off, entry_len, esha, entry, exc = r
                norm.normalize_entry(entry, "2018-05-07", "??", esha)
        print(time.time() - t0)


def test_simhash():
    s = "".join(str(x) for x in range(1000))
    assert norm.gen_simhash("") == 16_825_458_760_271_544_958
    assert norm.gen_simhash("hello") == 36_330_143_249_342_482
    assert norm.gen_simhash(s) == 816_031_085_364_464_265


def benchmark_simhash(benchmark):
    # debdeps: python3-pytest-benchmark
    for x in range(400):
        norm.gen_simhash(str(x))


def setup_module(module):
    fp.conf.devel = True
    fp.conf.interact = False
    fp.conf.vardir = Path("var/lib/fastpath")
    fp.conf.cachedir = fp.conf.vardir / "cache"
    fp.conf.s3cachedir = fp.conf.cachedir / "s3"
    fp.conf.sshcachedir = fp.conf.cachedir / "ssh"
