#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# See https://github.com/ooni/pipeline/blob/master/docs/delete-report.md
#

import argparse
import gzip
import json
import os

from contextlib import closing

import oonipl.can as can
import oonipl.tmp as tmp
from oonipl.const import LZ4_LEVEL
from oonipl.cli import dirname, filename
from oonipl.popen import ScopedPopen, PIPE

from canning import stream_canning


def canned_report_delete(
    src_root, index, affected, to_del, dst_root, index_dst, compress
):
    dst_base = os.path.dirname(index_dst)
    with tmp.open_tmp_gz(index_dst, chmod=0444) as fdindex:
        for row in index:
            if row["filename"] in affected:
                if "canned" not in row:
                    continue  # skip the row in index, do nothing to files
                for k in ("file_crc32", "file_sha1", "file_size", "text_size"):
                    row.pop(k, None)
                sentence = {_["textname"] for _ in row["canned"]} & to_del
                with open(
                    os.path.join(src_root, row["filename"]), "rb"
                ) as fdin, tmp.open_tmp(
                    os.path.join(dst_root, row["filename"]), chmod=0444
                ) as fdout, can.flistz_tempfile(
                    sentence
                ) as files_from, ScopedPopen(
                    [compress[0], "-d"], stdin=fdin, stdout=PIPE
                ) as decomp, ScopedPopen(
                    ["tar", "--delete", "--null", "--files-from", files_from],
                    stdin=decomp.stdout,
                    stdout=PIPE,
                ) as tar, ScopedPopen(
                    compress, stdin=tar.stdout, stdout=PIPE
                ) as comp:

                    csum = stream_canning(comp.stdout, fdout)
                    # NB: reverse order of the pipeline due to EPIPE propagation!
                    for proc, name in (
                        (comp, "~gzip"),
                        (tar, "tar"),
                        (decomp, "~zcat"),
                    ):
                        if proc.wait() != 0:
                            raise RuntimeError(
                                "Subprocess failure", name, proc, proc.returncode
                            )
                    row["file_crc32"] = csum["text_crc32"]
                    row["file_sha1"] = csum["text_sha1"]
                    row["file_size"] = csum["text_size"]
                row["canned"] = [
                    _ for _ in row["canned"] if _["textname"] not in sentence
                ]
            json.dump(row, fdindex, sort_keys=True)
            fdindex.write("\n")


def sanity_check(to_del, dst_root, index_dst):
    with closing(gzip.GzipFile(index_dst, mode="r")) as fdindex:
        for row in fdindex:
            row = json.loads(row)
            if "canned" in row:
                if {_["textname"] for _ in row["canned"]} & to_del:
                    raise RuntimeError(
                        "Destination index lists files to delete", row["filename"]
                    )
            elif row["textname"] in to_del:
                raise RuntimeError(
                    "Destination index lists files to delete", row["filename"]
                )
            filename = os.path.join(dst_root, row["filename"])
            if os.path.exists(filename):
                # some files may be absent after partial cleanup
                if os.path.getsize(filename) != row["file_size"]:
                    raise RuntimeError("File size mismatch", row["filename"])


def parse_args():
    p = argparse.ArgumentParser(
        description="ooni-pipeline: delete reports from canned and reports-tgz files"
    )

    g1 = p.add_mutually_exclusive_group(required=True)
    g1.add_argument(
        "--canned", metavar="DIR", type=dirname, help="Path to .../private/canned"
    )
    g1.add_argument(
        "--reports-tgz",
        metavar="DIR",
        type=dirname,
        help="Path to .../private/reports-tgz",
    )

    p.add_argument("--bucket", metavar="BUCKET", help="Bucket to check", required=True)

    g2 = p.add_mutually_exclusive_group(required=True)
    g2.add_argument("--list", action="store_true", help="List affected archives")
    g2.add_argument(
        "--dst", metavar="DIR", type=dirname, help="Path for repacked archives"
    )

    g3 = p.add_mutually_exclusive_group(required=True)
    g3.add_argument(
        "--files-from",
        metavar="FILE",
        type=filename,
        help="Get names to delete from FILE",
    )
    g3.add_argument("pathname", nargs="*", default=[], help="Files to delete")

    return p.parse_args()


def main():
    opt = parse_args()
    if opt.canned:
        src_root = opt.canned
        index_src = filename(os.path.join(src_root, opt.bucket, "index.json.gz"))
    elif opt.reports_tgz:
        src_root = opt.reports_tgz
        index_src = filename(os.path.join(src_root, opt.bucket + ".index.json.gz"))

    # NB: list of affected reports should be prefixed with bucket name, like following:
    # 2019-01-29/20190129T005236Z-RU-AS41661-web_connectivity-...-0.2.0-probe.json
    if opt.files_from:
        with open(opt.files_from) as fd:
            to_del = {l.rstrip() for l in fd}
    elif opt.pathname:
        to_del = set(opt.pathname)

    with open(index_src) as fd:
        index = can.load_index(fd)
    affected = {
        row["filename"]
        for row in index
        if ("canned" in row and any(_["textname"] in to_del for _ in row["canned"]))
        or ("canned" not in row and row["textname"] in to_del)
    }

    if opt.list:
        for arch in sorted(affected):
            print(arch)
    elif opt.dst:
        if opt.canned:
            index_dst = os.path.join(os.path.join(opt.dst, opt.bucket, "index.json.gz"))
            compress = ["lz4", LZ4_LEVEL]
            if not os.path.exists(os.path.join(opt.dst, opt.bucket)):
                os.mkdir(os.path.join(opt.dst, opt.bucket))
        else:
            index_dst = os.path.join(
                os.path.join(opt.dst, opt.bucket + ".index.json.gz")
            )
            compress = ["gzip"]
        if not os.path.exists(index_dst):
            canned_report_delete(
                src_root, index, affected, to_del, opt.dst, index_dst, compress
            )
        else:
            sanity_check(to_del, opt.dst, index_dst)


if __name__ == "__main__":
    main()
