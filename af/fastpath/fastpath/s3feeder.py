#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

Feeds reports from cans on S3 or local disk

Uses credentials from ~/.aws/config in the block:
[ooni-data-private]
aws_access_key_id = ...
aws_secret_access_key = ...

Explore bucket from CLI:
AWS_PROFILE=ooni-data-private aws s3 ls s3://ooni-data-private/canned/2019-07-16/

"""

from typing import Iterator
import logging
import os
import time
import tarfile

import lz4.frame as lz4frame  # debdeps: python3-lz4

# lz4frame appears faster than executing lz4cat: 2.4s vs 3.9s on a test file

import boto3  # debdeps: python3-boto3

from fastpath.normalize import iter_yaml_msmt_normalized
from fastpath.metrics import setup_metrics
from fastpath.mytypes import MsmtTup

AWS_PROFILE = "ooni-data"
BUCKET_NAME = "ooni-data"

log = logging.getLogger("fastpath")
metrics = setup_metrics(name="fastpath.s3feeder")

# suppress debug logs
for l in ("urllib3", "botocore", "s3transfer"):
    logging.getLogger(l).setLevel(logging.INFO)


def load_multiple(fn, touch=True) -> Iterator[MsmtTup]:
    """Load contents of cans. Decompress tar archives if found.
    Yields measurements one by one as:
        (string of JSON, None) or (None, msmt dict)
    """
    if touch:
        os.utime(fn)  # update access time - used for cache cleanup

    # TODO: handle:
    # RuntimeError: LZ4F_decompress failed with code: ERROR_decompressionFailed
    if fn.endswith(".tar.lz4"):
        with lz4frame.open(fn) as f:
            tf = tarfile.TarFile(fileobj=f)
            while True:
                m = tf.next()
                if m is None:
                    break
                log.debug("Loading nested %s", m.name)
                k = tf.extractfile(m)
                assert k is not None
                if m.name.endswith(".json"):
                    for line in k:
                        yield (line, None)

                elif m.name.endswith(".yaml"):
                    continue  # FIXME
                    bucket_tstamp = "FIXME"
                    for msm in iter_yaml_msmt_normalized(k, bucket_tstamp):
                        yield (None, msm)

    elif fn.endswith(".json.lz4"):
        with lz4frame.open(fn) as f:
            for line in f:
                yield (line, None)

    elif fn.endswith(".yaml.lz4"):
        with lz4frame.open(fn) as f:
            raise Exception("Unsupported format: YAML")
            bucket_tstamp = "FIXME"
            for msm in iter_yaml_msmt_normalized(f, bucket_tstamp):
                metrics.incr("yaml_normalization")
                yield (None, msm)

    else:
        raise RuntimeError(fn)


def create_s3_client():
    return boto3.Session(profile_name=AWS_PROFILE).client("s3")


def list_cans_on_s3(prefix):
    # TODO list files based on date and return them
    s3 = create_s3_client()
    r = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix="canned/" + prefix)
    for filedesc in r["Contents"]:
        fn = filedesc["Key"]
        size = filedesc["Size"]
        print("%s size %d MB" % (fn, size / 1024 / 1024))


def list_cans_on_s3_for_a_day(s3, day):
    prefix = f"{day}/"
    r = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix="canned/" + prefix)
    files = []
    assert "Contents" in r
    for filedesc in r["Contents"]:
        fname = filedesc["Key"][7:]  # trim away "canned/"
        files.append((fname, filedesc["Size"]))
    return files


@metrics.timer("fetch_cans")
def fetch_cans(s3, conf, files):
    """
    Download cans to a local directory
    fnames = [("2013-09-12/20130912T150305Z-MD-AS1547-http_", size), ... ]
    """
    # fn: can filename without path
    # diskf: File in the s3cachedir directory
    to_dload = set()
    for fn, size in files:
        diskf = conf.s3cachedir / fn
        if diskf.exists() and size == diskf.stat().st_size:
            metrics.incr("cache_hit")
            diskf.touch(exist_ok=True)
        else:
            metrics.incr("cache_miss")
            to_dload.add((fn, diskf, size))

    if not to_dload:
        return

    def _cb(bytes_count):
        if _cb.start_time is None:
            _cb.start_time = time.time()
            _cb.count = bytes_count
            return
        _cb.count += bytes_count
        _cb.total_count += bytes_count
        metrics.gauge("s3_download_percentage", _cb.total_count / _cb.total_size * 100)
        try:
            speed = _cb.count / 131_072 / (time.time() - _cb.start_time)
            metrics.gauge("s3_download_speed_avg_Mbps", speed)
        except ZeroDivisionError:
            pass

    _cb.total_size = sum(t[2] for t in to_dload)
    _cb.total_count = 0

    for fn, diskf, size in to_dload:
        s3fname = os.path.join("canned", fn)
        # TODO: handle missing file
        log.info("Downloading can %s size %d MB" % (fn, size / 1024 / 1024))
        diskf.parent.mkdir(parents=True, exist_ok=True)
        metrics.gauge("fetching", 1)
        _cb.start_time = None
        with diskf.open("wb") as f:
            s3.download_fileobj(BUCKET_NAME, s3fname, f, Callback=_cb)
        metrics.gauge("fetching", 0)
        assert size == diskf.stat().st_size

    metrics.gauge("s3_download_speed_avg_Mbps", 0)


@metrics.timer("fetch_cans_for_a_day_with_cache")
def fetch_cans_for_a_day_with_cache(conf, day):
    s3 = create_s3_client()
    fns = list_cans_on_s3_for_a_day(s3, day)
    fetch_cans(s3, conf, fns)
