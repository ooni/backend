#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
"""
This script is used to delete raw reports in uncompressed form to ensure they
are stored compressed as canned .tar.gz files.
"""

import argparse
import gzip
import json
import os

from canning import load_verified_index, listdir_filesize
from oonipl.cli import dirname
from oonipl.jsonz import jsonl_gz, json_gz


def cleanup_reports_raw(reports_raw_root, bucket, texts):
    dirname = os.path.join(reports_raw_root, bucket)
    if not os.path.exists(dirname):
        return  # non-existent dir is empty :-)
    ls_raw = listdir_filesize(dirname)
    for fname, size in ls_raw:
        idfname = "{}/{}".format(bucket, fname)
        if (idfname, size) not in texts:
            raise RuntimeError(
                "reports-raw have a file that is not canned & tgz'ed",
                bucket,
                fname,
                size,
            )
    for fname, size in ls_raw:
        os.unlink(os.path.join(reports_raw_root, bucket, fname))


def parse_args():
    # that was prievo
    p = argparse.ArgumentParser(
        description="ooni-pipeline: remove files from private/reports-raw that are stored as `canned` and `reports-tgz`"
    )
    p.add_argument("--bucket", metavar="BUCKET", help="Bucket to check", required=True)
    p.add_argument(
        "--reports-raw-root",
        metavar="DIR",
        type=dirname,
        help="Path to .../private/reports-raw",
        required=True,
    )
    p.add_argument(
        "--canned-index",
        metavar="FNAME",
        type=jsonl_gz,
        help="Path to .../canned/YYYY-MM-DD/index.json.gz",
        required=True,
    )
    p.add_argument(
        "--reports-tgz-index",
        metavar="FNAME",
        type=json_gz,
        help="Path to .../reports-tgz/YYYY-MM-DD.index.json.gz",
        required=True,
    )
    opt = p.parse_args()
    return opt


def compare_index_texts(canned_index, reports_tgz_index):
    canned = set()
    for tar in canned_index:
        if "canned" in tar:
            for c in tar["canned"]:
                canned.add((c["textname"], c["text_size"]))
        else:
            canned.add((tar["textname"], tar["text_size"]))
    tgz = {(c["textname"], c["text_size"]) for c in reports_tgz_index["canned"]}
    if canned != tgz:
        raise RuntimeError("Two archives have different indexes")
    return tgz


def main():
    opt = parse_args()
    texts = compare_index_texts(opt.canned_index, opt.reports_tgz_index)
    prefix = opt.bucket + "/"
    for textname, _ in texts:
        if not textname.startswith(prefix):
            raise RuntimeError(
                "Index textname prefix does not match bucket", bucket, textname
            )
    cleanup_reports_raw(opt.reports_raw_root, opt.bucket, texts)


if __name__ == "__main__":
    main()
