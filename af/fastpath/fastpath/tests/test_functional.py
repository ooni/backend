"""
Simulate feeding from the collectors or cans on S3 using a local can
"""

from pathlib import Path
import hashlib
import logging
import os
import time

import ujson
import boto3  # debdeps: python3-boto3
import pytest  # debdeps: python3-pytest

import fastpath.core as fp

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
    log.info(json.dumps(o, sort_keys=True, ensure_ascii=False, indent=2))


# TODO mock out metrics


def setup_module(module):
    fp.conf.devel = True
    fp.conf.interact = False
    fp.conf.vardir = Path("var/lib/fastpath")
    fp.conf.cachedir = fp.conf.vardir / "cache"
    fp.conf.s3cachedir = fp.conf.cachedir / "s3"
    fp.conf.sshcachedir = fp.conf.cachedir / "ssh"
