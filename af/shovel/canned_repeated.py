#!/usr/bin/env python2.7
"""
This is used to populate the repeated_report table with duplicate report_id.

It's not used regularly, but it should be run when a report with a duplicate
report_id is detected or measurements with duplicate measurement_id.
"""

import argparse
import functools
import glob
import gzip
import hashlib
import json
import os
from base64 import (
    b64decode,
)  # NB b64encode != str.encode('base64'), b64encode does not add newlines
from contextlib import closing
from subprocess import PIPE

import psycopg2

from canning import INDEX_FNAME
from oonipl.pg import PGCopyFrom, pg_quote, pg_binquote
from oonipl.cli import dirname
from oonipl.popen import ScopedPopen


def get_repeated_sha1(files):
    # to avoid keeping 300Mb+ (and counting) in RAM
    env = {"LC_ALL": "C"}
    with ScopedPopen(["sort"], stdin=PIPE, stdout=PIPE, env=env) as sort, ScopedPopen(
        ["uniq", "--repeated"], stdin=sort.stdout, stdout=PIPE, env=env
    ) as uniq:
        for fname in files:
            with gzip.GzipFile(fname, "r") as index:
                for line in index:
                    line = json.loads(line)
                    if "canned" in line:
                        for line in line["canned"]:
                            sort.stdin.write(line["text_sha1"])
                            sort.stdin.write("\n")
                    else:
                        sort.stdin.write(line["text_sha1"])
                        sort.stdin.write("\n")
        sort.stdin.close()  # signal EOF
        repeated_sha1 = {_.rstrip("\n") for _ in uniq.stdout}
        if sort.wait() != 0:
            raise RuntimeError("sort failed with non-zero returncode", sort.returncode)
        if uniq.wait() != 0:
            raise RuntimeError("uniq failed with non-zero returncode", uniq.returncode)
    return repeated_sha1


def iter_repeated(files, repeated_sha1):
    for fname in files:
        with gzip.GzipFile(fname, "r") as index:
            for line in index:
                line = json.loads(line)
                if "canned" in line:
                    for canned in line["canned"]:
                        if canned["text_sha1"] in repeated_sha1:
                            yield line, canned
                else:
                    if line["text_sha1"] in repeated_sha1:
                        yield line, line


# Some prankster may push SHA1 collision to the pipeline. So here is SHA512 safety net.
def text_sha512(blob, text):
    if "canned" in blob:
        cmd = ["tar", "-I", "lz4", "--extract", "--to-stdout", text["textname"]]
    else:
        cmd = ["lz4", "-d"]
    h = hashlib.sha512()
    with ScopedPopen(cmd, stdin=open(blob["filename"]), stdout=PIPE) as proc:
        for c in iter(functools.partial(proc.stdout.read, 131072), ""):
            h.update(c)
        if proc.wait() != 0:
            raise RuntimeError(
                "cmd failed with non-zero returncode", cmd, proc.returncode
            )
    return h.digest()


def parse_args():
    p = argparse.ArgumentParser(
        description="ooni-pipeline: private/canned -> duplicate reports"
    )
    p.add_argument(
        "--canned-root", metavar="DIR", type=dirname, help="Path to .../private/canned"
    )
    p.add_argument("--postgres", metavar="DSN", help="libpq data source name")
    return p.parse_args()


def repeated_to_stdout(it):
    for blob, text in it:
        print text["text_sha1"], text_sha512(blob, text).encode("base64"), text[
            "textname"
        ], blob["filename"]


def repeated_to_postgres(it, pgconn):
    with pgconn.cursor() as c:
        c.execute(
            """CREATE TEMPORARY TABLE dup (
                textname text UNIQUE NOT NULL,
                orig_sha1 sha1 NOT NULL,
                orig_sha512 sha512 NOT NULL
            ) ON COMMIT DROP"""
        )
        with closing(
            PGCopyFrom(pgconn, "dup", columns=("textname", "orig_sha1", "orig_sha512"))
        ) as w:
            for blob, text in it:
                orig_sha1 = b64decode(text["text_sha1"])
                orig_sha512 = text_sha512(blob, text)
                w.write(
                    "{}\t{}\t{}\n".format(
                        pg_quote(text["textname"]),
                        pg_binquote(orig_sha1),
                        pg_binquote(orig_sha512),
                    )
                )

        # no changed hashes
        c.execute(
            """SELECT COUNT(*) FROM repeated_report rr JOIN dup ON (
            rr.textname = dup.textname AND (
            rr.orig_sha1 != dup.orig_sha1 OR rr.orig_sha512 != dup.orig_sha512))"""
        )
        if c.fetchone()[0] != 0:
            raise RuntimeError("WTF: file changes it hashsum across time")

        c.execute(
            """
        -- delete already known duplicates
        DELETE FROM dup
        WHERE (textname, orig_sha1, orig_sha512) IN (
            SELECT textname, orig_sha1, orig_sha512 FROM repeated_report)
        ;

        -- SHA512 match is enough to consider report a duplicate
        INSERT INTO repeated_report (dupgrp_no, used, textname, orig_sha1, orig_sha512)
        SELECT
            (SELECT DISTINCT dupgrp_no
             FROM repeated_report
             WHERE orig_sha1 = dup.orig_sha1 AND orig_sha512 = dup.orig_sha512),
            false, textname, orig_sha1, orig_sha512
        FROM dup
        WHERE (orig_sha1, orig_sha512) IN (SELECT orig_sha1, orig_sha512 FROM repeated_report)
        ;
        DELETE FROM dup
        WHERE (orig_sha1, orig_sha512) IN (SELECT orig_sha1, orig_sha512 FROM repeated_report)
        ;

        -- ingest new duplicate reports, oldest one in the group is used by default
        INSERT INTO repeated_report (dupgrp_no, used, textname, orig_sha1, orig_sha512)
        SELECT
            dupgrp_no,
            row_number() OVER (PARTITION BY orig_sha1, orig_sha512 ORDER BY textname) = 1,
            textname, orig_sha1, orig_sha512
        FROM (
            SELECT nextval('dupgrp_no_seq') dupgrp_no, orig_sha1, orig_sha512
            FROM dup GROUP BY orig_sha1, orig_sha512
        ) grpsha
        JOIN dup USING (orig_sha1, orig_sha512)
        ;
        DELETE FROM dup
        WHERE (textname, orig_sha1, orig_sha512) IN (
            SELECT textname, orig_sha1, orig_sha512 FROM repeated_report)
        ;
        """
        )

        # Okay, I don't know what to do with remaining rows. There should be none.
        c.execute("SELECT COUNT(*) FROM dup")
        if c.fetchone()[0] != 0:
            raise RuntimeError("WTF: unprocessed duplicate report records")


def main():
    opt = parse_args()
    if opt.canned_root:
        os.chdir(
            opt.canned_root
        )  # the easiest way to handle relative path is to avoid handling
    files = sorted(glob.glob("20??-??-??/" + INDEX_FNAME))
    repeated_sha1 = get_repeated_sha1(files)
    it = iter_repeated(files, repeated_sha1)
    if opt.postgres:
        with closing(psycopg2.connect(dsn=opt.postgres)) as pgconn:  # close on end
            with pgconn:  # commit transaction
                repeated_to_postgres(it, pgconn)
    else:
        repeated_to_stdout(it)


if __name__ == "__main__":
    main()
