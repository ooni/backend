#
# Fastpath - YAML normalization func tests
#

from io import BytesIO
from pathlib import Path
import hashlib
import logging
import os

import boto3  # debdeps: python3-boto3
import gzip
import lz4.frame as lz4frame  # debdeps: python3-lz4
import pytest
import requests
import tarfile
import ujson

import fastpath.normalize as norm
from fastpath.s3feeder import create_s3_client

log = logging.getLogger()


## Fixtures


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
        vn="2013-05-05/20130505T103213Z-VN-AS24173-http_requests-no_report_id-0.1.0-probe.yaml.lz4",
        yaml16="2016-07-07/20160706T000046Z-GB-AS9105-http_requests-TYXZLcFg4yUp9Io2LrOMM7CjLk0QcIdsMPiCZtVgkxUrTxnFM0GiMbr8iGDl3OEe-0.1.0-probe.yaml.lz4",
        yaml17="2017-12-21/20171220T153044Z-BE-AS5432-dns_consistency-mnKRlHuqk8Eo6XMJt5ZkVQrgReaEXPEWaO9NafgXxSVIhAswTXT7QJc6zhsuttpK-0.1.0-probe.yaml.lz4",
        yaml18="2018-03-21/20180320T211810Z-NL-AS1103-dns_consistency-yiCRUmXy6MndqnV3g5QYBKGich5OwP9cQQfOiYnxYAfZatgQZlStuWIT30yu586R-0.1.0-probe.yaml.lz4",
        # yaml2014hr1="2014-02-20/http_requests.1.tar.lz4",
        yaml2014dns="2014-02-20/dns_consistency.0.tar.lz4",
        # yaml2014mpt="2014-02-20/multi_protocol_traceroute.0.tar.lz4",
        yaml2014hr0="2014-02-20/http_requests.0.tar.lz4",
        yaml2014hh="2014-02-20/http_host.0.tar.lz4",
        yaml2014hfm="2014-02-20/http_header_field_manipulation.0.tar.lz4",
    )
    for k, v in _cans.items():
        _cans[k] = Path("testdata") / v

    to_dload = sorted(f for f in _cans.values() if not f.is_file())
    if not to_dload:
        return _cans

    bname = "ooni-data"
    s3 = create_s3_client()
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


@pytest.fixture(scope="session", params=["2015-07-01"])
# @pytest.fixture(scope="session", params=["2015-07-01", "2015-07-02"])
def autoclaved_io(request):
    ## Fetch autoclaved reports to compare the outputs of normalization
    bucket_date = request.param
    assert bucket_date.startswith("20")

    boto3.setup_default_session(profile_name="ooni-data-private")
    s3 = boto3.resource("s3")

    def list_tarballs_with_yaml_texts(target_bucket):
        """Fetch YAML text names from index.json.gz
        yield filenames that contain enough YAML files
        e.g. '2015-07-02/dns_n_http.0.tar.lz4',
        """
        log.info("RAW Fetching index for %s", target_bucket)
        obj = s3.Object(
            "ooni-data-private", "canned/{}/index.json.gz".format(target_bucket)
        )
        index_data = obj.get()["Body"].read()
        for line in gzip.decompress(index_data).split(b"\n"):
            if not line:
                continue
            j = ujson.loads(line)
            tarball_name = j["filename"]
            yaml_count = 0
            if "canned" in j:
                for c in j["canned"]:
                    if c["textname"].endswith("yaml"):
                        yaml_count += 1

            elif j["textname"].endswith("yaml"):
                yaml_count += 1

            if yaml_count > 3:
                yield tarball_name

    def extract_yaml_reports(filename):
        """Fetch compressed tarball from S3 private repo
        yield any YAML report
        """
        # Local caching - disabled
        # if os.path.isfile(filename):
        #     with open(filename, "rb") as f:
        #         fileobj=BytesIO(f.read())
        #         fileobj.seek(0)
        # else:
        #     obj = s3.Object("ooni-data-private", "canned/{}".format(filename))
        #     fileobj = BytesIO(lz4frame.decompress(obj.get()["Body"].read()))
        #     with open(filename, "wb") as f:
        #         fileobj.seek(0)
        #         f.write(fileobj.read())
        #     fileobj.seek(0)
        obj = s3.Object("ooni-data-private", "canned/{}".format(filename))
        fileobj = BytesIO(lz4frame.decompress(obj.get()["Body"].read()))

        tf = tarfile.TarFile(fileobj=fileobj)
        for m in tf.getmembers():
            if m.name.endswith(".yaml"):
                f = tf.extractfile(m)
                canned_yaml = BytesIO(f.read())
                yield (m.name, canned_yaml)

    def fetch_autoclaved_json(name):
        url = "https://api.ooni.io/files/download/{}".format(name)
        log.info("AC Fetching %s", url)
        return requests.get(url).text

    data = []
    for tarball_name in list_tarballs_with_yaml_texts(bucket_date):
        # Extract YAML reports from a tarball
        # Then fetch the related autoclaved file from the API
        # (it's a set of JSON documents separated by newline but in a file
        # with yaml extension)
        log.info("RAW Tarball: %s", tarball_name)
        for name, rawblob in extract_yaml_reports(tarball_name):
            log.info("RAW Found YAML: %s", name)
            autoclaved_json = fetch_autoclaved_json(name)
            autoclaved_msmts = [ujson.loads(m) for m in autoclaved_json.splitlines()]
            log.info("AC Autoclaved msmts: %d", len(autoclaved_msmts))
            data.append((name, bucket_date, rawblob, autoclaved_msmts))
            # break # speedup tests

    log.info(">>> Returning %d items", len(data))
    return data


## Utils


def hash(j):
    # deterministic hash to compare entries
    jstr = ujson.dumps(j, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.shake_128(jstr).hexdigest(4)


## Tests


@pytest.mark.skip(reason="Broken")
def test_compare_normalized_with_autoclaved(autoclaved_io):
    for fname, bucket_tstamp, yaml_bytes, autoclaved_msmts in autoclaved_io:
        log.info("Normalizing %s", fname)
        log.info("len autoclaved msmts %d", len(autoclaved_msmts))
        g = norm.iter_yaml_msmt_normalized(yaml_bytes, bucket_tstamp)
        normalized_msmts = list(g)
        assert len(normalized_msmts) == len(autoclaved_msmts)

        a_mst = list(i["measurement_start_time"] for i in autoclaved_msmts)
        n_mst = list(i["measurement_start_time"] for i in normalized_msmts)
        assert a_mst == n_mst

        for n in range(len(autoclaved_msmts)):
            autoclaved = autoclaved_msmts[n]
            normalized = normalized_msmts[n]
            log.info(n)
            for k, v in sorted(autoclaved.items()):
                log.info("K %s", k)
                if isinstance(v, dict):
                    for k1, v1 in sorted(v.items()):
                        log.info("K1 %s->%s", k, k1)
                        assert v1 == normalized[k][k1]

                else:
                    assert v == normalized[k]


@pytest.mark.skip(reason="Broken")
def test_normalize_json(cans):
    can = "testdata/2018-05-07/20180506T014008Z-CN-AS4134-web_connectivity-20180506T014010Z_AS4134_ZpxhAVt3iqCjT5bW5CfJspbqUcfO4oZfzDVjCWAu2UuVkibFsv-0.2.0-probe.json.lz4"
    with open(can) as f:
        j = ujson.load(f)
    expected = {0: "977713ee", 1: "42ec375e", 2: "9bec4a5f", 3: "a38504ed"}
    for n, entry in enumerate(j):
        esha = b"x" * 20
        entry = norm.normalize_entry(entry, "2018-05-07", "??", esha)
        if n in expected:
            assert hash(entry) == expected[n]


def test_generate_report_id_empty():
    header = {}
    report_id = norm.generate_report_id(header)
    exp = "19700101T010000Z_KWnRnnxAmNrJfoqrTxAKhVDgGkiuSYfGDSecYaayqhcqlfOXCX"
    assert report_id == exp


def test_generate_report_id():
    header = dict(probe_cc="UK", test_name="web_connectivity")
    report_id = norm.generate_report_id(header)
    exp = "19700101T010000Z_LLWQMcPHNefGtRNzxcgKlXlSjKmRuyyKLycBDGwNiNEbMztVzb"
    assert report_id == exp


@pytest.mark.skip(reason="Broken")
def test_normalize_yaml_brokenframe(cans):
    # BrokenFrameError
    # can = cans["yaml2014hh"]
    # can = cans["yaml2014dns"]
    # can = cans["yaml2014hr0"]
    can = cans["yaml2014hfm"]
    can = can.as_posix()

    for n, r in enumerate(norm.iter_yaml_lz4_reports(can)):
        entry = norm.normalize_entry(entry, "2018-05-07", "??", esha)


# from datetime import date
# from test_functional import s3msmts
# def test_normalize_yaml_2013():
#    cans = s3msmts("http_requests", date(2013, 12, 1), date(2013, 12, 2))
# def test_normalize_yaml_2016


def test_normalize_yaml_2016(cans):
    can = cans["yaml16"]
    canfn = can.as_posix()
    assert canfn.startswith("testdata/2016-07-07/20160706T000046Z-GB")
    day = canfn.split("/")[1]
    rfn = canfn.split("/", 1)[1][:-4]  # remove testdata/ and .lz4
    with lz4frame.open(can) as f:
        for n, entry in enumerate(norm.iter_yaml_msmt_normalized(f, day, rfn)):
            ujson.dumps(entry)  # ensure it's serializable
            if n == 0:
                with open("fastpath/tests/data/yaml16_0.json") as f:
                    exp = ujson.load(f)
                assert entry == exp
            elif n > 20:
                break


def test_normalize_yaml_dns_consistency_2017(cans):
    can = cans["yaml17"]
    canfn = can.as_posix()
    day = canfn.split("/")[1]
    rfn = canfn.split("/", 1)[1][:-4]  # remove testdata/ and .lz4
    # s3://ooni-data/autoclaved/jsonl.tar.lz4/2017-12-21/20171220T153044Z-BE-AS5432-dns_consistency-mnKRlHuqk8Eo6XMJt5ZkVQrgReaEXPEWaO9NafgXxSVIhAswTXT7QJc6zhsuttpK-0.1.0-probe.yaml.lz4
    # lz4cat <fn> | head -n1 | jq -S . > fastpath/tests/data/yaml17_0.json
    with lz4frame.open(can) as f:
        for n, entry in enumerate(norm.iter_yaml_msmt_normalized(f, day, rfn)):
            ujson.dumps(entry)  # ensure it's serializable
            if n == 0:
                with open("fastpath/tests/data/yaml17_0.json") as f:
                    exp = ujson.load(f)
                assert entry == exp
            elif n > 20:
                break


def test_normalize_yaml_dns_consistency_2018(cans):
    can = cans["yaml18"]
    canfn = can.as_posix()
    day = canfn.split("/")[1]
    rfn = canfn.split("/", 1)[1][:-4]  # remove testdata/ and .lz4
    with lz4frame.open(can) as f:
        for n, entry in enumerate(norm.iter_yaml_msmt_normalized(f, day, rfn)):
            ujson.dumps(entry)  # ensure it's serializable


def test_simhash():
    s = "".join(str(x) for x in range(1000))
    assert norm.gen_simhash("") == 16_825_458_760_271_544_958
    assert norm.gen_simhash("hello") == 36_330_143_249_342_482
    assert norm.gen_simhash(s) == 816_031_085_364_464_265


def benchmark_simhash(benchmark):
    # debdeps: python3-pytest-benchmark
    for x in range(400):
        norm.gen_simhash(str(x))
