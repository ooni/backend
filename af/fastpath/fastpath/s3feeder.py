#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Feeds reports from cans on public S3 bucke or local disk

Explore bucket from CLI:
AWS_PROFILE=ooni-data aws s3 ls s3://ooni-data/canned/2019-07-16/

"""

from datetime import date, timedelta
from typing import Generator
from pathlib import Path
import logging
import os
import time
import tarfile

import lz4.frame as lz4frame  # debdeps: python3-lz4
import ujson

# lz4frame appears faster than executing lz4cat: 2.4s vs 3.9s on a test file

import boto3  # debdeps: python3-boto3
from botocore import UNSIGNED as botoSigUNSIGNED
from botocore.config import Config as botoConfig

from fastpath.normalize import iter_yaml_msmt_normalized
from fastpath.metrics import setup_metrics
from fastpath.mytypes import MsmtTup

CAN_BUCKET_NAME = "ooni-data"
MC_BUCKET_NAME = "ooni-data-eu-fra"

log = logging.getLogger("fastpath")
metrics = setup_metrics(name="fastpath.s3feeder")

# suppress debug logs
for l in ("urllib3", "botocore", "s3transfer"):
    logging.getLogger(l).setLevel(logging.INFO)


def load_multiple(fn: str) -> Generator[MsmtTup, None, None]:
    """Load contents of cans. Decompress tar archives if found.
    Yields measurements one by one as:
        (string of JSON, None, None) or (None, msmt dict, None)
    """
    # TODO: handle:
    # RuntimeError: LZ4F_decompress failed with code: ERROR_decompressionFailed
    if fn.endswith(".tar.lz4"):
        with lz4frame.open(fn) as f:
            tf = tarfile.TarFile(fileobj=f)
            while True:
                m = tf.next()
                if m is None:
                    # end of tarball
                    break
                log.debug("Loading nested %s", m.name)
                k = tf.extractfile(m)
                assert k is not None
                if m.name.endswith(".json"):
                    for line in k:
                        yield (line, None, None)

                elif m.name.endswith(".yaml"):
                    bucket_tstamp = fn.split("/")[-2]
                    rfn = f"{bucket_tstamp}/" + fn.split("/")[-1]
                    for msm in iter_yaml_msmt_normalized(k, bucket_tstamp, rfn):
                        metrics.incr("yaml_normalization")
                        yield (None, msm, None)

    elif fn.endswith(".json.lz4"):
        with lz4frame.open(fn) as f:
            for line in f:
                yield (line, None, None)

    elif fn.endswith(".yaml.lz4"):
        with lz4frame.open(fn) as f:
            bucket_tstamp = fn.split("/")[-2]
            rfn = f"{bucket_tstamp}/" + fn.split("/")[-1]
            for msm in iter_yaml_msmt_normalized(f, bucket_tstamp, rfn):
                metrics.incr("yaml_normalization")
                yield (None, msm, None)

    elif fn.endswith(".tar.gz"):
        # minican with missing gzipping :(
        tf = tarfile.open(fn)
        while True:
            m = tf.next()
            if m is None:
                # end of tarball
                tf.close()
                break
            log.debug("Loading %s", m.name)
            k = tf.extractfile(m)
            assert k is not None
            if not m.name.endswith(".post"):
                log.error("Unexpected filename")
                continue

            try:
                j = ujson.loads(k.read())
            except Exception:
                log.error(repr(k[:100]), exc_info=1)

            fmt = j.get("format", "")
            if fmt == "json":
                msm = j.get("content", {})
                yield (None, msm, None)

            elif fmt == "yaml":
                log.info("Skipping YAML")

            else:
                log.info("Ignoring invalid post")

    elif fn.endswith("/index.json.gz"):
        pass

    else:
        raise RuntimeError(f"Unexpected [mini]can filename '{fn}'")


def create_s3_client():
    return boto3.client("s3", config=botoConfig(signature_version=botoSigUNSIGNED))


def list_cans_on_s3_for_a_day(s3, day: date):
    """List legacy cans."""
    prefix = f"{day}/"
    r = s3.list_objects_v2(Bucket=CAN_BUCKET_NAME, Prefix="canned/" + prefix)

    if ("Contents" in r) ^ (day <= date(2020, 10, 21)):
        # The last day with cans is 2020-10-21
        log.warn("%d can files found!", len(r.get("Contents", [])))

    fs = r.get("Contents", [])
    files = [(f["Key"], f["Size"]) for f in fs]
    return files


def list_minicans_on_s3_for_a_day(s3, day: date):
    """List minicans."""
    # s3cmd ls s3://ooni-data-eu-fra/raw/20210202
    tstamp = day.strftime("%Y%m%d")
    prefix = f"raw/{tstamp}/"
    cont_token = None
    files = []
    # list_objects_v2 returns 1000 objects max and needs a token (!= None)
    while True:
        kw = {} if cont_token is None else dict(ContinuationToken=cont_token)
        r = s3.list_objects_v2(Bucket=MC_BUCKET_NAME, Prefix=prefix, **kw)

        cont_token = r.get("NextContinuationToken", None)
        if ("Contents" in r) ^ (day >= date(2020, 10, 20)):
            # The first day with minicans is 2020-10-20
            log.warn("%d minican files found!", len(r.get("Contents", [])))

        for f in r.get("Contents", []):
            if f["Key"].endswith(".tar.gz"):
                files.append((f["Key"], f["Size"]))

        if cont_token is None:
            return files


@metrics.timer("fetch_cans")
def fetch_cans(s3, conf, files) -> Generator[Path, None, None]:
    """
    Download cans to a local directory
    fnames = [("2013-09-12/20130912T150305Z-MD-AS1547-http_", size), ... ]
    yield each can file Path
    """
    # fn: can filename without path
    # diskf: File in the s3cachedir directory
    cans = set()  # (s3fname, filename on disk, size, download required)
    for s3fname, size in files:
        diskf = conf.s3cachedir / s3fname.split("/", 1)[1]
        if diskf.exists() and size == diskf.stat().st_size:
            metrics.incr("cache_hit")
            diskf.touch(exist_ok=True)
            cans.add((s3fname, diskf, size, False))
        else:
            metrics.incr("cache_miss")
            cans.add((s3fname, diskf, size, True))

    def _cb(bytes_count):
        if _cb.start_time is None:
            _cb.start_time = time.time()
            _cb.count = bytes_count
            return
        _cb.count += bytes_count
        _cb.total_count += bytes_count
        metrics.gauge("s3_download_percentage", _cb.total_count / _cb.total_size * 100)
        # log.debug("s3_download_percentage %d", _cb.total_count / _cb.total_size * 100)
        try:
            speed = _cb.count / 131_072 / (time.time() - _cb.start_time)
            metrics.gauge("s3_download_speed_avg_Mbps", speed)
        except ZeroDivisionError:
            pass

    _cb.total_size = sum(t[2] for t in cans if t[3])
    _cb.total_count = 0

    for s3fname, diskf, size, dload_required in cans:
        if not dload_required:
            yield diskf  # already in local cache
            continue

        # TODO: handle missing file
        log.info("Downloading can %s size %d MB" % (s3fname, size / 1024 / 1024))
        diskf.parent.mkdir(parents=True, exist_ok=True)
        tmpf = diskf.with_suffix(".s3tmp")
        metrics.gauge("fetching", 1)
        _cb.start_time = None
        with tmpf.open("wb") as f:
            bucket_name = CAN_BUCKET_NAME if "canned/" in s3fname else MC_BUCKET_NAME
            s3.download_fileobj(bucket_name, s3fname, f, Callback=_cb)
            f.flush()
            os.fsync(f.fileno())
        metrics.gauge("fetching", 0)
        tmpf.rename(diskf)
        assert size == diskf.stat().st_size
        yield diskf

    metrics.gauge("s3_download_speed_avg_Mbps", 0)


# TODO: merge with stream_daily_cans, add caching to the latter to be used
# during functional tests
# @metrics.timer("fetch_cans_for_a_day_with_cache")
# def fetch_cans_for_a_day_with_cache(conf, day):
#     s3 = create_s3_client()
#     fns = list_cans_on_s3_for_a_day(s3, day)
#     list(fetch_cans(s3, conf, fns))


def _calculate_etr(t0, now, start_day, day, stop_day, can_num, can_tot_count) -> int:
    """Estimate total runtime in seconds.
    stop_day is not included, can_num starts from 0
    """
    tot_days_count = (stop_day - start_day).days
    elapsed = now - t0
    days_done = (day - start_day).days
    fraction_of_day_done = (can_num + 1) / float(can_tot_count)
    etr = elapsed * tot_days_count / (days_done + fraction_of_day_done)
    return etr


def _update_eta(t0, start_day, day, stop_day, can_num, can_tot_count):
    """Generate metric process_s3_measurements_eta expressed as epoch"""
    try:
        now = time.time()
        etr = _calculate_etr(t0, now, start_day, day, stop_day, can_num, can_tot_count)
        eta = t0 + etr
        metrics.gauge("process_s3_measurements_eta", eta)
    except:
        pass


def stream_cans(conf, start_day: date, end_day: date) -> Generator[MsmtTup, None, None]:
    """Stream cans from S3"""
    # TODO: implement new postcan format as well
    today = date.today()
    if not start_day or start_day >= today:
        return

    log.info("Fetching older cans from S3")
    t0 = time.time()
    day = start_day
    s3 = create_s3_client()
    # the last day is not included
    stop_day = end_day if end_day < today else today
    while day < stop_day:
        log.info("Processing day %s", day)
        cans_fns = list_cans_on_s3_for_a_day(s3, day)
        minicans_fns = list_minicans_on_s3_for_a_day(s3, day)
        cans_fns.extend(minicans_fns)
        for cn, can_f in enumerate(fetch_cans(s3, conf, cans_fns)):
            try:
                _update_eta(t0, start_day, day, stop_day, cn, len(cans_fns))
                #log.info("can %s ready", can_f.name)
                for msmt_tup in load_multiple(can_f.as_posix()):
                    yield msmt_tup
            except Exception as e:
                log.error(str(e), exc_info=True)

            if not conf.keep_s3_cache:
                try:
                    can_f.unlink()
                except FileNotFoundError:
                    pass

        day += timedelta(days=1)

    if end_day:
        log.info(f"Reached {end_day}, streaming cans from S3 finished")
        return
