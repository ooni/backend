#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# It SHOULD be run after successful `check_sanitised` run, that's why it requires `santoken`.
"""
This was used to cleanup chameleon sanitised files.
"""

import argparse
import gzip
import json
import os

import autoclaving
from canning import listdir_filesize
from check_sanitised import calc_santoken
from cleanup_reports_raw import s3_ls_jsongz
from oonipl.cli import dirname


def cleanup_sanitised(sanitised_root, autoclaved_root, bucket, s3_ls):
    if "public/sanitised/" not in s3_ls["metadata"]["url"]:
        raise RuntimeError("Unexpected s3.metadata.url", s3_ls["metadata"])
    s3_size = {
        "/".join(_["file_name"].rsplit("/", 2)[-2:]): _["file_size"]
        for _ in s3_ls["results"]
    }

    autoclaved_reports = set()  # with `.json` extention instead of `.yaml`
    with gzip.GzipFile(
        os.path.join(autoclaved_root, bucket, autoclaving.INDEX_FNAME)
    ) as fd:
        for _, doc in autoclaving.stream_json_blobs(fd):
            if '"report"' in doc:
                doc = json.loads(doc)
                if doc["type"] == "report":
                    textname = doc["textname"]
                    if textname[-5:] == ".yaml":
                        textname = textname[:-5] + ".json"
                    autoclaved_reports.add(textname)

    # FIXME: technically it's a race, santoken may be already stale
    for fname, size in listdir_filesize(os.path.join(sanitised_root, bucket)):
        idfname = "{}/{}".format(bucket, fname)
        if s3_size.get(idfname) == size and idfname in autoclaved_reports:
            os.unlink(os.path.join(sanitised_root, bucket, fname))
        else:
            print idfname, "FS:", size, "S3:", s3_size.get(
                idfname
            ), "autoclaved:", idfname in autoclaved_reports


def parse_args():
    p = argparse.ArgumentParser(
        description="ooni-pipeline: remove files from public/sanitised that are stored in public/autoclaved and listed in s3"
    )
    p.add_argument("--bucket", metavar="BUCKET", help="Bucket to check", required=True)
    p.add_argument(
        "--sanitised-root",
        metavar="DIR",
        type=dirname,
        help="Path to .../public/sanitised",
        required=True,
    )
    p.add_argument(
        "--autoclaved-root",
        metavar="DIR",
        type=dirname,
        help="Path to .../public/autoclaved",
        required=True,
    )
    p.add_argument(
        "--s3-ls",
        metavar="S3_LS",
        type=s3_ls_jsongz,
        help="Path to s3-ls.json.gz output of aws_s3_ls.py",
        required=True,
    )
    p.add_argument(
        "--santoken",
        metavar="FILE",
        type=file,
        help="Token for checked sanitised directory",
        required=True,
    )
    opt = p.parse_args()
    # that's not `os.path.join` to verify _textual_ value of the option
    dirname("{}/{}".format(opt.sanitised_root, opt.bucket))
    dirname("{}/{}".format(opt.autoclaved_root, opt.bucket))
    opt.santoken = opt.santoken.read()
    return opt


def main():
    opt = parse_args()
    santoken = calc_santoken(opt.sanitised_root, opt.autoclaved_root, opt.bucket)
    if santoken != opt.santoken:
        raise RuntimeError("Stale santoken", opt.santoken, santoken)
    cleanup_sanitised(opt.sanitised_root, opt.autoclaved_root, opt.bucket, opt.s3_ls)


if __name__ == "__main__":
    main()
