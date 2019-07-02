#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import argparse
import os

from oonipl.cli import dirname, filename
from oonipl.jsonz import json_gz


def parse_args():
    p = argparse.ArgumentParser(
        description="ooni-pipeline: cleanup uploaded files from a dir"
    )
    p.add_argument(
        "--s3-ls",
        metavar="S3_LS",
        type=json_gz,
        help="Path to s3-ls.json.gz output of aws_s3_ls.py",
        required=True,
    )
    p.add_argument(
        "--dir", metavar="DIR", type=dirname, help="Directory to cleanup", required=True
    )
    p.add_argument(
        "--exclude",
        metavar="FNAME",
        type=filename,
        nargs="+",
        default=[],
        help="Files to preserve",
    )
    opt = p.parse_args()
    return opt


def main():
    opt = parse_args()
    s3 = {
        os.path.basename(_["file_name"]): _["file_size"] for _ in opt.s3_ls["results"]
    }
    if len(s3) != len(opt.s3_ls["results"]):
        raise RuntimeError("S3 file_name collision", opt.dir, opt.s3_ls["metadata"])
    for ex in opt.exclude:  # excluded files must also be uploaded
        fs_size = os.path.getsize(ex)
        ex = os.path.basename(ex)
        if s3[ex] != fs_size:
            raise RuntimeError(
                "Excluded file has different size at S3", ex, fs_size, s3[ex]
            )
        del s3[ex]
    for fname, s3_size in s3.iteritems():  # first -- check
        fpath = os.path.join(opt.dir, fname)
        if os.path.exists(fpath) and os.path.getsize(fpath) != s3_size:
            raise RuntimeError(
                "File size at DIR and S3 differ", fname, opt.dir, s3_size
            )
    for fname in s3:  # second -- unlink
        fpath = os.path.join(opt.dir, fname)
        if os.path.exists(fpath):
            os.unlink(fpath)


if __name__ == "__main__":
    main()
