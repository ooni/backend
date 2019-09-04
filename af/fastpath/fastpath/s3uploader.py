#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

Upload measurements and other data in S3

WARNING: the data is made public immediately.

Uses credentials from ~/.aws/config in the block:
[ooni-data]
aws_access_key_id = ...
aws_secret_access_key = ...

Run uploader from CLI:
python3 s3uploader.py

Explore bucket from CLI:
AWS_PROFILE=ooni-data aws s3 ls s3://ooni-data

"""

import logging

# import lz4.frame as lz4frame  # debdeps: python3-lz4

from datetime import datetime, timedelta, timezone
import ujson
import boto3  # debdeps: python3-boto3

try:
    from fastpath.metrics import setup_metrics
except ImportError:
    from metrics import setup_metrics

log = logging.getLogger("fastpath.s3uploader")
metrics = setup_metrics(name="fastpath.s3uploader")

AWS_PROFILE = "ooni-data"
BUCKET_NAME = "ooni-data"
UPLOAD_PREFIX = "fastpath/"

# suppress debug logs
for l in ("urllib3", "botocore", "s3transfer"):
    logging.getLogger(l).setLevel(logging.INFO)


def create_s3_client():
    boto3.setup_default_session(profile_name=AWS_PROFILE)
    return boto3.client("s3")


@metrics.timer("list_files")
def list_files(s3, prefix=""):
    """List files
    """
    files = []
    list_kwargs = dict(Bucket=BUCKET_NAME, Prefix=UPLOAD_PREFIX + prefix)
    while True:
        r = s3.list_objects_v2(**list_kwargs)
        if "Contents" not in r:
            break
        files.extend(r["Contents"])
        if r["IsTruncated"] == False:
            break
        list_kwargs["ContinuationToken"] = r["NextContinuationToken"]

    return files


def _delete_files(s3, files):
    """Delete files in chunks of 1000 each
    """
    files = [{"Key": f["Key"]} for f in files]
    while files:
        deleters, files = files[:1000], files[1000:]
        r = s3.delete_objects(Bucket=BUCKET_NAME, Delete=dict(Objects=deleters))
        cnt = len(r["Deleted"])
        log.debug("%d files deleted", cnt)


@metrics.timer("purge_files")
def purge_files(s3, tdelta, prefix=""):
    """Delete files older than a time delta
    """
    threshold = datetime.now(timezone.utc) - tdelta
    files = list_files(s3, prefix=prefix)
    files = [f for f in files if f["LastModified"] < threshold]
    metrics.gauge("files_to_delete", len(files))
    log.debug("%d files to delete", len(files))
    _delete_files(s3, files)


@metrics.timer("upload_measurement")
def upload_measurement(s3, msmt: dict, fname: str):
    """Serialize and upload a measurement
    """
    s3r = boto3.resource("s3")
    obj = s3r.Object(BUCKET_NAME, UPLOAD_PREFIX + fname)
    obj.put(Body=ujson.dumps(msmt))


def main():
    s3 = create_s3_client()
    for n in range(1100):
      upload_measurement(s3, dict(n=n), f"s3uploader_test_{n}.json")
    t = timedelta(seconds=10)
    purge_files(s3, t, prefix="s3uploader_test_")
    t = timedelta(seconds=0)
    purge_files(s3, t, prefix="s3uploader_test_")


if __name__ == "__main__":
    main()
