#!/usr/bin/env python2

import argparse
import gzip
import json
import os
import re
from datetime import datetime
from subprocess import check_call, check_output

from oonipl.tmp import ScopedTmpdir

if datetime.fromtimestamp(0) != datetime(1970, 1, 1, 0, 0, 0):
    raise RuntimeError("awscli requires TZ=UTC")


def parse_args():
    p = argparse.ArgumentParser(
        description="ooni-pipeline: tar -I lz4 --extract *.tar.lz4 | aws s3 sync"
    )
    p.add_argument(
        "--src",
        metavar="SRC_PATH",
        help="Source to decompress *.lz4 files from",
        required=True,
    )
    p.add_argument(
        "--s3-bucket",
        metavar="BUCKET",
        help="Destination S3 bucket upload files to",
        required=True,
    )
    p.add_argument(
        "--s3-prefix",
        metavar="PREFIX",
        help="S3 bucket prefix to upload files to",
        required=True,
    )
    opt = p.parse_args()
    return opt


def strip_prefix(s, prefix):
    l = len(prefix)
    if s[:l] == prefix:
        return s[l:]
    raise ValueError("No expected prefix", prefix, s)


def setitem_new(mapping, key, value):
    if key not in mapping:
        mapping[key] = value
    else:
        raise LookupError("Key already exists", key, mapping[key], value)


def aws_s3_ls(s3_bucket, s3_prefix):
    # that's CLI call to avoid dealiing with pagination
    if len(s3_prefix) and s3_prefix[-1] != "/":
        s3_prefix += "/"
    s3obj = check_output(
        ["aws", "s3api", "list-objects", "--bucket", s3_bucket, "--prefix", s3_prefix]
    )
    if (
        len(s3obj) == 0
    ):  # prefix absence is a special case, s3api gives empty stdout and zero exit-code
        return {}
    s3obj = json.loads(s3obj)
    if s3obj.keys() != ["Contents"]:
        raise RuntimeError("Unexpected keys in `aws s3api list-objects`", s3obj.keys())
    ls = {}
    for el in s3obj["Contents"]:
        # mtime = datetime.datetime.strptime(el['LastModified'], '%Y-%m-%dT%H:%M:%S.000Z')
        # mtime = int(time.mktime(mtime.timetuple())) # needs TZ=UTC
        name = strip_prefix(el["Key"], s3_prefix)
        setitem_new(ls, name, el["Size"])
    return ls


AUTOCLAVED_INDEX_FNAME = "index.json.gz"


def autoclaved_index_ls(path):
    prefix = os.path.basename(path) + "/"  # 'YYYY-MM-DD/'
    ls_report, report2file, ls_file = {}, {}, {}
    with gzip.GzipFile(os.path.join(path, AUTOCLAVED_INDEX_FNAME), "r") as indexfd:
        refilter = re.compile(r'"(?:/?file|report)"')
        for line in indexfd:
            if refilter.search(line):
                line = json.loads(line)
                if line["type"] == "file":
                    # {"filename": "2017-08-28/web_connectivity.02.tar.lz4", "type": "file"}
                    filename = strip_prefix(line["filename"], prefix)
                elif line["type"] == "report":
                    # {"orig_sha1": "Fax...AVc=", "src_size": 18267142, "textname": "2017-08-28/20170827T005240Z-RU-...robe.json", "type": "report"}
                    textname = strip_prefix(line["textname"], prefix)
                    setitem_new(ls_report, textname, line["src_size"])
                    setitem_new(report2file, textname, filename)
                elif line["type"] == "/file":
                    # {"file_crc32": 927831702, "file_sha1": "OSVZy4G4MaKizTNl5m3+LGoSdW4=", "file_size": 14463389, "type": "/file"}
                    setitem_new(ls_file, filename, line["file_size"])
                    del filename
    return ls_report, report2file, ls_file


def aws_s3_lz4cat_sync(src, s3_bucket, s3_prefix):
    date = os.path.basename(src)
    if not s3_prefix.endswith("/" + date):
        raise RuntimeError("S3 bucket prefix is not YYYY-MM-DD", date)
    ls_report, report2file, ls_file = autoclaved_index_ls(src)
    aws_report = aws_s3_ls(s3_bucket, s3_prefix)

    extra = (
        aws_report.viewkeys() - ls_report.viewkeys()
    )  # FIXME: update to `viewitems()` when `src_size` is fixed for report
    if extra:
        # FIXME: that should be updated to respect some sort of mtime when pipeline-based PII scrubbing is rolled out
        raise RuntimeError(
            "S3 bucket has unknown files", extra
        )  # files with mismatching size also trigger that

    missing = (
        ls_report.viewkeys() - aws_report.viewkeys()
    )  # FIXME: update to `viewitems()` when `src_size` is fixed for report
    file_to_unpack = {}
    for textname in missing:
        file_to_unpack.setdefault(report2file[textname], set()).add(textname)

    # Decompressing files chunk-by-chunk saves Linux kernel page cache from
    # pollution.  It's possible to stream files from local lz4 to S3 without
    # touching the disk and it *seems* to be easy and reasonable to do that, as
    # 80% of the volume consists of "large" reports, but `aws s3 cp` does not
    # use `--expected-size` to check for unexpected EOF from stdin and counting
    # bytes in python is not something I want to do. Also, `aws s3 cp`
    # pre-buffers large blobs in RAM to speedup upload, so streaming is not as
    # beneficial as expected in terms of RAM savings.
    # See also https://github.com/aws/aws-cli/issues/2390
    for filename, missing_textname in file_to_unpack.iteritems():
        with ScopedTmpdir(prefix="oolz42s3") as tmpdir:  # OO lz4 to s3 :-)
            filepath = os.path.join(src, filename)
            if os.path.getsize(filepath) != ls_file[filename]:
                raise RuntimeError(
                    "Unexpected size of compressed file",
                    filepath,
                    os.path.getsize(filepath),
                    ls_file[filename],
                )

            if filename.endswith(".tar.lz4"):
                check_call(
                    [
                        "tar",
                        "--use-compress-program",
                        "lz4",
                        "--directory",
                        tmpdir,
                        "--extract",
                        "--file",
                        os.path.join(src, filename),
                    ]
                )
            elif filename.endswith((".json.lz4", ".yaml.lz4")):
                os.mkdir(os.path.join(tmpdir, date))
                destname = filename[: -len(".lz4")]
                check_call(
                    [
                        "lz4",
                        "--decompress",
                        os.path.join(src, filename),
                        os.path.join(tmpdir, date, destname),
                    ]
                )
            else:
                raise RuntimeError(
                    "Unexpected filename in the directory", src, filename
                )

            if os.listdir(tmpdir) != [
                date
            ]:  # check if bucket name is there and correct
                raise RuntimeError(
                    "Unexpected archive content, something besides usual date", date
                )

            extra = set(os.listdir(os.path.join(tmpdir, date))) - missing_textname
            for textname in extra:
                os.unlink(os.path.join(tmpdir, date, textname))
            # FIXME: bring it back when `src_size` is fixed for report
            # for textname in missing_textname:
            #    st_size = os.path.getsize(os.path.join(tmpdir, date, textname))
            #    if st_size != ls_report[textname]:
            #        raise RuntimeError('Unexpected size of report', textname, st_size, ls_report[textname])

            check_call(
                [
                    "aws",
                    "s3",
                    "cp",
                    "--recursive",
                    os.path.join(tmpdir, date),
                    "s3://{}/{}".format(s3_bucket, s3_prefix),
                ]
            )


def main():
    opt = parse_args()
    aws_s3_lz4cat_sync(opt.src, opt.s3_bucket, opt.s3_prefix)


if __name__ == "__main__":
    main()
