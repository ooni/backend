#!/usr/bin/env python2

import argparse
import gzip
import json
import os
import subprocess
import tempfile
import time

from contextlib import closing

from canning import load_verified_index, listdir_filesize, stream_canning
from oonipl.cli import dirname
from oonipl.tmp import ScopedTmpdir


def filelist_from_canndx(canned_index):
    filelist = []
    for caninfo in canned_index:
        if "canned" in caninfo:
            filelist.extend(caninfo["canned"])
        else:
            filelist.append(
                {
                    k: caninfo[k]
                    for k in ("text_crc32", "text_sha1", "text_size", "textname")
                }
            )
    return filelist


def tar_reports_raw(tar_dir, reports_root, canned_root, bucket):
    reports_dir = os.path.join(reports_root, bucket)
    prefix = bucket + "/"
    reports = set(prefix + _ for _ in os.listdir(reports_dir))
    canned_index = load_verified_index(os.path.join(canned_root, bucket), bucket)
    tarred_index_fname = os.path.join(tar_dir, "{}.index.json.gz".format(bucket))
    if os.path.exists(tarred_index_fname):
        with gzip.GzipFile(tarred_index_fname, "rb") as gzfd:
            tarred_index = json.load(gzfd)
            if tarred_index["canned"] == filelist_from_canndx(
                canned_index
            ):  # does not respect order
                print "reports-tgz bucket {} is already done".format(bucket)
                return
        raise RuntimeError("reports-tgz index does not match canned", bucket)
    if len(reports) == 0:
        print "Refilling empty reports-raw dir at {}".format(reports_dir)
        for caninfo in canned_index:
            if "canned" in caninfo:
                with ScopedTmpdir(dir=reports_dir) as tmpdir:
                    subprocess.check_call(
                        [
                            "tar",
                            "--extract",
                            "-I",
                            "lz4",
                            "--file",
                            os.path.join(canned_root, caninfo["filename"]),
                            "--directory",
                            tmpdir,
                        ]
                    )
                    for c in caninfo["canned"]:
                        assert c["textname"].startswith(prefix)
                        os.rename(
                            os.path.join(tmpdir, c["textname"]),
                            os.path.join(reports_dir, c["textname"][len(prefix) :]),
                        )
                    os.rmdir(os.path.join(tmpdir, bucket))  # fail if not empty
                    assert not os.listdir(tmpdir)
            else:
                assert caninfo["textname"].startswith(prefix)
                out = os.path.join(reports_dir, caninfo["textname"][len(prefix) :])
                with tempfile.NamedTemporaryFile(dir=reports_dir) as fdout, open(
                    os.path.join(canned_root, caninfo["filename"]), "rb"
                ) as fdin:
                    subprocess.check_call(["lz4", "-d"], stdin=fdin, stdout=fdout)
                    os.link(fdout.name, out)
                os.chmod(out, 0444)
        os.chmod(reports_dir, 0555)
    else:
        print "Verifying non-empty reports-raw dir at {}".format(reports_dir)
        canned_reports = set()
        for caninfo in canned_index:
            if "canned" in caninfo:
                canned_reports.update(_["textname"] for _ in caninfo["canned"])
            else:
                canned_reports.add(caninfo["textname"])
        if canned_reports != reports:
            raise RuntimeError(
                "private/reports-raw and private/canned index Mismatch", bucket
            )

    tarred_index = {  # following `canned` schema, it's single tar file with whole bucket
        "canned": filelist_from_canndx(canned_index),
        "filename": "{}.tar.gz".format(bucket),
    }
    out = os.path.join(tar_dir, tarred_index["filename"])
    print "Compressing {} from {} to {}".format(bucket, reports_root, out)
    with tempfile.NamedTemporaryFile(dir=tar_dir) as fdout:
        subprocess.check_call(
            [
                "tar",
                "--create",
                "--gzip",
                "--file",
                fdout.name,
                "--directory",
                reports_root,
                bucket,
            ]
        )
        os.link(fdout.name, out)
    os.chmod(out, 0444)
    with open(out, "rb") as fd:
        # that's done as a separate step (not as a `tar` pipe reader) for simplicity
        tar_meta = stream_canning(fd)
    # NB: `text_size` of compressed tar file is not stored!
    tarred_index["file_crc32"] = tar_meta["text_crc32"]
    tarred_index["file_sha1"] = tar_meta["text_sha1"]
    tarred_index["file_size"] = tar_meta["text_size"]
    tarred_index["file_mtime"] = int(os.path.getmtime(out))

    print "Writing index for {} to {}".format(
        tarred_index["filename"], tarred_index_fname
    )
    with tempfile.NamedTemporaryFile(dir=tar_dir) as fdout:
        with closing(
            gzip.GzipFile(
                filename="{}.index.json".format(bucket),
                mtime=tarred_index["file_mtime"],
                mode="wb",
                fileobj=fdout,
            )
        ) as gzout:
            json.dump(tarred_index, gzout, sort_keys=True)
            gzout.write("\n")
        os.link(fdout.name, tarred_index_fname)
    os.chmod(tarred_index_fname, 0444)


def parse_args():
    p = argparse.ArgumentParser(
        description="ooni-pipeline: create private/reports-tgz from private/reports-raw or private/canned"
    )
    p.add_argument("--bucket", metavar="BUCKET", help="Bucket to check", required=True)
    p.add_argument(
        "--reports-tgz",
        metavar="DIR",
        type=dirname,
        help="Path to .../private/reports-tgz",
        required=True,
    )
    p.add_argument(
        "--reports-raw",
        metavar="DIR",
        type=dirname,
        help="Path to .../private/reports-raw",
        required=True,
    )
    p.add_argument(
        "--canned",
        metavar="DIR",
        type=dirname,
        help="Path to .../private/canned",
        required=True,
    )
    opt = p.parse_args()
    # that's not `os.path.join` to verify _textual_ value of the option
    dirname("{}/{}".format(opt.reports_raw, opt.bucket))
    dirname("{}/{}".format(opt.canned, opt.bucket))
    return opt


def main():
    opt = parse_args()
    tar_reports_raw(opt.reports_tgz, opt.reports_raw, opt.canned, opt.bucket)


if __name__ == "__main__":
    main()
