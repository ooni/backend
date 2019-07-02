#!/usr/bin/env python2

# FIXME: kill this ugly parser and replace it with `aws s3api list-objects`

import argparse
import gzip
import json
import os
import re
import tempfile
import time
from contextlib import closing
from datetime import datetime
from subprocess import check_output

if datetime.fromtimestamp(0) != datetime(1970, 1, 1, 0, 0, 0):
    raise RuntimeError("awscli requires TZ=UTC")


def parse_args():
    p = argparse.ArgumentParser(
        description="ooni-pipeline: AWS S3 -> list of bucket files"
    )
    p.add_argument(
        "--url",
        metavar="S3_URL",
        help="Url to pass to `aws s3 ls --recursive`",
        required=True,
    )
    p.add_argument(
        "--s3-ls",
        metavar="S3_LS",
        help="Path to destination s3-ls.json.gz file",
        required=True,
    )
    opt = p.parse_args()
    return opt


def aws_s3_ls(url):
    now = time.time()
    ls = check_output(["aws", "s3", "ls", "--recursive", url])
    file_re = re.compile(
        r"^(?P<day>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2})\s+(?P<size>\d+) (?P<name>.*)$"
    )
    results = []
    unparsed = []
    for line in ls.splitlines():
        m = file_re.match(line)
        if m and m.group("name"):
            results.append(
                {
                    "file_mtime": "{day}T{time}Z".format(**m.groupdict()),
                    "file_size": int(m.group("size")),
                    "file_name": m.group("name"),
                }
            )
        else:
            unparsed.append(line)
    results.sort(key=lambda x: x["file_name"])
    if unparsed:
        raise RuntimeError("Unparsed lines", unparsed)
    return {
        "metadata": {
            "time": datetime.fromtimestamp(int(now)).isoformat() + "Z",
            "recursive": True,
            "url": url,
        },
        "results": results,
    }


def main():
    opt = parse_args()
    with tempfile.NamedTemporaryFile(
        prefix="tmps3ls", dir=os.path.dirname(opt.s3_ls)
    ) as fdraw:
        with closing(
            gzip.GzipFile(filename="s3-ls.json", mode="wb", fileobj=fdraw)
        ) as fd:
            data = aws_s3_ls(opt.url)
            json.dump(data, fd, sort_keys=True)
        os.link(fdraw.name, opt.s3_ls)
    os.chmod(opt.s3_ls, 0444)


if __name__ == "__main__":
    main()
