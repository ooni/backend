#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import os

# This is needed to make daily_workflow work
os.environ["TZ"] = "UTC"

import gzip
import functools
import json
import random
import shutil
import string
import subprocess
import sys
import tempfile
import time
import unittest
from base64 import b64encode

import psycopg2

from centrifugation import httpt_body, exc_hash, pop_values, ChecksummingTee, NopTeeFd
from oonipl.pg import PGCopyFrom, pg_quote, _pg_unquote


def _httpt_body(body, te=None):
    d = {"body": body, "headers": {}}
    if te is not None:
        d["headers"]["TrAnSfEr-EnCoDiNg"] = te
    return httpt_body(d)


class TestChunked(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_httpt_body(""), "")
        self.assertEqual(_httpt_body("0\r\n\r\n", "chunked"), "")

    def test_chunked(self):
        self.assertEqual(
            _httpt_body(
                "4\r\nasdf\r\n" "3\r\nqwe\r\n" "2\r\nzx\r\n" "0\r\n\r\n", "chunked"
            ),
            "asdfqwezx",
        )
        self.assertEqual(
            _httpt_body(
                u"2\r\nzx\r\n"
                u"8\r\nпсой\r\n"  # NB: 8 bytes for 4 symbols!
                u"0\r\n\r\n",
                "chunked",
            ),
            u"zxпсой".encode("utf-8"),
        )

    def test_broken(self):
        raw = "2\r\nzx\r\n" "7\r\nFilast\xf2\r\n" "0\r\n\r\n"
        self.assertEqual(_httpt_body(raw, "chunked"), "zxFilast\xf2")
        # NB: can't be properly de-chunked after <meta/> charset decoding
        uni = raw.decode("ISO-8859-1")
        self.assertEqual(_httpt_body(uni, "chunked"), uni.encode("utf-8"))


class TestPGQuoting(unittest.TestCase):
    def test_bool(self):
        self.assertEqual(pg_quote(True), "TRUE")
        self.assertEqual(pg_quote(False), "FALSE")

    def test_bits(self):
        blob = u"".join(map(unichr, xrange(1, 256))).encode("utf-8")
        self.assertEqual(blob, _pg_unquote(pg_quote(blob)))
        self.assertEqual(u"\ufffd".encode("utf-8"), pg_quote(u"\u0000"))
        self.assertEqual(u"\ufffd".encode("utf-8"), pg_quote("\0"))

    def test_ugly(self):
        blob = r"\\n"
        self.assertEqual(blob, _pg_unquote(pg_quote(blob)))


PG = os.getenv("UNITTEST_PG")


class TestE2EQuoting(unittest.TestCase):
    # Run like that:
    # $ UNITTEST_PG='host=spbmeta user=postgres' python test_centrifugation.py TestE2EQuoting
    def setUp(self):
        self.conn = psycopg2.connect(dsn=PG)
        self.table = "tmptbl" + "".join(
            random.choice(string.lowercase) for _ in xrange(6)
        )

    def tearDown(self):
        self.conn.close()

    @unittest.skipUnless(PG, "No PostgreSQL")
    def test_string(self):
        for mapfn in (chr, unichr):
            with self.conn, self.conn.cursor() as c:
                c.execute(
                    "CREATE TEMPORARY TABLE {} (nnn int2, ccc text) ON COMMIT DROP".format(
                        self.table
                    )
                )
                dest = PGCopyFrom(self.conn, self.table, wbufsize=64)
                for i in xrange(1, 128):  # postgresql does not support \x00 in body
                    dest.write("{:d}\t{}\n".format(i, pg_quote(mapfn(i))))
                dest.close()
                c.execute("SELECT * FROM {}".format(self.table))
                nrows = 0
                for nnn, ccc in c:
                    self.assertEqual(nnn, ord(ccc))
                    nrows += 1
                self.assertEqual(nrows, 127)

    @unittest.skipUnless(PG, "No PostgreSQL")
    def test_array(self):
        for mapfn in (chr, unichr):
            with self.conn, self.conn.cursor() as c:
                c.execute(
                    "CREATE TEMPORARY TABLE {} (nnn int2, ccc text[]) ON COMMIT DROP".format(
                        self.table
                    )
                )
                dest = PGCopyFrom(self.conn, self.table, wbufsize=64)
                for i in xrange(1, 128):  # postgresql does not support \x00 in body
                    dest.write(
                        "{:d}\t{}\n".format(
                            i, pg_quote([mapfn(i), "a", mapfn(i), "b", mapfn(i)])
                        )
                    )
                dest.close()
                c.execute("SELECT * FROM {}".format(self.table))
                nrows = 0
                for nnn, ccc in c:
                    self.assertEqual(
                        ccc, [mapfn(nnn), "a", mapfn(nnn), "b", mapfn(nnn)]
                    )
                    nrows += 1
                self.assertEqual(nrows, 127)

    @unittest.skipUnless(PG, "No PostgreSQL")
    def test_badrow_sink(self):
        for rowno in xrange(9):
            for ver in xrange(1 << rowno):
                isgood = bin(ver)[2:].rjust(rowno, "0") if rowno else ""
                with self.conn, self.conn.cursor() as c:
                    c.execute(
                        "CREATE TEMPORARY TABLE good{} (t text) ON COMMIT DROP".format(
                            self.table
                        )
                    )
                    c.execute(
                        "CREATE TEMPORARY TABLE bad{} (tbl text, code_ver integer, datum bytea) ON COMMIT DROP".format(
                            self.table
                        )
                    )
                    bad = PGCopyFrom(self.conn, "bad" + self.table)
                    good = PGCopyFrom(self.conn, "good" + self.table, badsink=bad)
                    for ndx, digit in enumerate(isgood):
                        row = ("<>{}<>" if digit == "1" else "<>{}<\0>").format(ndx)
                        good.write(row + "\n")
                    good.close()
                    bad.close()
                    # okay, let's check
                    c.execute("SELECT t FROM good{}".format(self.table))
                    good_set = set(_[0] for _ in c)
                    c.execute("SELECT datum FROM bad{}".format(self.table))
                    bad_blob = "|".join(str(_[0]) for _ in c)
                    # print rowno, ver, repr(isgood), good_set, repr(bad_blob)
                    for ndx, digit in enumerate(isgood):
                        row = ("<>{}<>" if digit == "1" else "<>{}<\0>").format(ndx)
                        if digit == "1":
                            self.assertIn(row, good_set)
                        else:
                            self.assertIn(row, bad_blob)
                    # COMMIT


class TestPartialReprocessing(unittest.TestCase):
    # Run like that:
    # $ UNITTEST_PG='host=spbmeta user=oopguser' python test_centrifugation.py TestPartialReprocessing
    def setUp(self):
        self.conn = psycopg2.connect(dsn=PG)
        self.tmpdir = None
        self.mkdtemp(None)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmpdir)
        self.tmpdir = None

    def mkdtemp(self, bucket):
        if self.tmpdir is not None:
            shutil.rmtree(self.tmpdir)
            self.tmpdir = None
        self.tmpdir = tempfile.mkdtemp()
        if bucket is not None:
            os.mkdir(os.path.join(self.tmpdir, bucket))

    @staticmethod
    def take_part_of_bucket(acroot, bucket):
        files = os.listdir(os.path.join(acroot, bucket))
        # some filtering to speedup processing and reduce data volume
        httpreq_blob = sorted(
            _ for _ in files if "-http_requests-" in _ and _.endswith(".lz4")
        )
        webcon_blob = sorted(
            _ for _ in files if "-web_connectivity-" in _ and _.endswith(".lz4")
        )
        webcon_tar = sorted(
            _
            for _ in files
            if _.startswith("web_connectivity.") and _.endswith(".tar.lz4")
        )  # OONI Probe
        questionable = set(httpreq_blob + webcon_blob + webcon_tar)
        to_keep = set(webcon_blob[:2] + webcon_tar[:2] + httpreq_blob[:2])
        modify = {webcon_tar[0], webcon_blob[0]}
        add = {webcon_tar[2]}
        files = {
            _
            for _ in files
            if _.endswith(".lz4") and (_ not in questionable or _ in to_keep)
        }
        return files, modify, add

    @staticmethod
    def calc_cksum(fname):
        with open(fname, "r") as fd:
            fd = ChecksummingTee(fd, NopTeeFd)
            for _ in iter(functools.partial(fd.read, 4096), ""):
                pass
            cksum = (fd.size, fd.crc32, fd.sha1)
        return cksum

    def test_reprocessing(self):
        acroot, bucket = "/srv/autoclaved", "2017-08-28"
        with self.conn, self.conn.cursor() as c:
            # almost every table besides `fingerprint`
            c.execute(
                "TRUNCATE TABLE autoclaved, badmeta, badrow, dns_a, domain, http_control, http_request, http_request_fp, http_verdict, input, label, measurement, report, residual, software, tcp, vanilla_tor"
            )

        files, modify, add = self.take_part_of_bucket(acroot, bucket)

        # create usual bucket
        self.mkdtemp(bucket)
        for f in files:
            os.symlink(
                os.path.join(acroot, bucket, f), os.path.join(self.tmpdir, bucket, f)
            )
        self.make_bucket_index(acroot, bucket, files, {})
        rc, _ = self.call_centrifugation("basic import")
        assert rc == 0, "centrifugation failed"
        self.retry_centrifugation()

        with self.conn, self.conn.cursor() as c:
            c.execute(
                """UPDATE autoclaved SET code_ver = 0
                         WHERE filename = '2017-08-28/web_connectivity.00.tar.lz4'"""
            )
            magic = self.get_magic_numbers(c, "2017-08-28/web_connectivity.00.tar.lz4")
        rc, _ = self.call_centrifugation("reprocess: UPDATE SET code_ver = 0")
        assert rc == 0
        self.retry_centrifugation()
        with self.conn, self.conn.cursor() as c:
            self.assertEqual(
                magic,
                self.get_magic_numbers(c, "2017-08-28/web_connectivity.00.tar.lz4"),
            )
            # TODO: there is no easy way to verify that no rows were touched as `xmin` is not naive "trx id"

        LZ4_EMPTY_FRAME = "\x04\x22\x4d\x18\x64\x40\xa7\x00\x00\x00\x00\x05\x5d\xcc\x02"

        addendum = add.pop()
        shutil.copyfile(
            os.path.join(acroot, bucket, addendum),
            os.path.join(self.tmpdir, bucket, addendum),
        )
        with open(os.path.join(self.tmpdir, bucket, addendum), "a") as fd:
            fd.write(LZ4_EMPTY_FRAME)
        self.make_bucket_index(acroot, bucket, files | {addendum}, {})
        rc, _ = self.call_centrifugation("cksum mismatch")
        assert rc == 1, "Hashsum mismatch should lead to failure"

        self.make_bucket_index(
            acroot,
            bucket,
            files | {addendum},
            {addendum: self.calc_cksum(os.path.join(self.tmpdir, bucket, addendum))},
        )
        rc, _ = self.call_centrifugation("new file added")
        assert rc == 0
        self.retry_centrifugation()

        self.make_bucket_index(acroot, bucket, files, {})
        rc, _ = self.call_centrifugation("file removed")
        assert rc == 1, "File removal should lead to failure"

        alter = modify.pop()
        os.unlink(os.path.join(self.tmpdir, bucket, alter))
        shutil.copyfile(
            os.path.join(acroot, bucket, alter),
            os.path.join(self.tmpdir, bucket, alter),
        )
        with open(os.path.join(self.tmpdir, bucket, alter), "a") as fd:
            fd.write(LZ4_EMPTY_FRAME)
        self.make_bucket_index(
            acroot,
            bucket,
            files | {addendum, alter},
            {
                addendum: self.calc_cksum(os.path.join(self.tmpdir, bucket, addendum)),
                alter: self.calc_cksum(os.path.join(self.tmpdir, bucket, alter)),
            },
        )
        with self.conn, self.conn.cursor() as c:
            magic = self.get_magic_numbers(c, "{}/{}".format(bucket, alter))
        rc, _ = self.call_centrifugation("one altered file")
        assert rc == 0
        self.retry_centrifugation()
        with self.conn, self.conn.cursor() as c:
            self.assertEqual(
                magic, self.get_magic_numbers(c, "{}/{}".format(bucket, alter))
            )

    def get_magic_numbers(self, c, filename):
        c.execute(
            "SELECT autoclaved_no FROM autoclaved WHERE filename = %s", [filename]
        )
        autoclaved_no = sorted(_[0] for _ in c)
        c.execute(
            """SELECT report_no
            FROM autoclaved
            JOIN report USING (autoclaved_no)
            WHERE filename = %s""",
            [filename],
        )
        report_no = sorted(_[0] for _ in c)
        c.execute(
            """SELECT msm_no
            FROM autoclaved
            JOIN report USING (autoclaved_no)
            JOIN measurement USING (report_no)
            WHERE filename = %s""",
            [filename],
        )
        measurement_no = sorted(_[0] for _ in c)
        return autoclaved_no, report_no, measurement_no

    def retry_centrifugation(self):
        # re-try over same bucket once again
        rc, delay = self.call_centrifugation("last state retry")
        assert rc == 0, "centrifugation failed"
        assert delay < 1, "Ultra-slow retry"

    def call_centrifugation(self, msg):
        print " ==> centrifugation.py:", msg
        start = time.time()
        rc = subprocess.call(
            [
                "./centrifugation.py",
                "--start",
                "2017-08-28T00:00:00",
                "--end",
                "2017-08-29T00:00:00",
                "--autoclaved-root",
                self.tmpdir,
                "--postgres",
                PG,
            ]
        )
        end = time.time()
        print " ^^^ centrifugation.py: rc = {:d}, duration = {:1f} sec".format(
            rc, end - start
        )
        return rc, end - start

    def make_bucket_index(self, acroot, bucket, files, cksum):
        files = {"{}/{}".format(bucket, f) for f in files}
        cksum = {"{}/{}".format(bucket, f): v for f, v in cksum.iteritems()}
        with gzip.GzipFile(
            os.path.join(acroot, bucket, "index.json.gz"), "r"
        ) as src, gzip.GzipFile(
            os.path.join(self.tmpdir, bucket, "index.json.gz"), "w"
        ) as dst:
            use, filename = False, None
            for line in src:
                if 'file"' in line:
                    doc = json.loads(line)
                    if doc["type"] == "file":
                        filename = doc["filename"]
                        use = filename in files
                        if use:
                            dst.write(line)
                    elif doc["type"] == "/file":
                        if not use:
                            pass
                        elif filename in cksum:
                            doc["file_size"], doc["file_crc32"], doc[
                                "file_sha1"
                            ] = cksum[filename]
                            doc["file_sha1"] = b64encode(doc["file_sha1"])
                            dst.write(json.dumps(doc) + "\n")
                        else:
                            dst.write(line)
                        use, filename = False, None
                    else:
                        raise RuntimeError("BUG: malicious data not handled")
                elif use:
                    dst.write(line)


class TextExcHash(unittest.TestCase):
    def deep_throw(self):
        import socket

        socket.create_connection(("127.126.125.124", 1))  # ECONREFUSED

    def test_stack_dependence(self):
        try:
            self.deep_throw()
        except Exception:
            einfo1 = sys.exc_info()
        # NB: functools.partial does not add stack frame
        self.deep_throw = lambda fn=self.deep_throw: fn()
        try:
            self.deep_throw()
        except Exception:
            einfo2 = sys.exc_info()
        self.assertEqual(einfo1[0], einfo2[0])  # same type
        self.assertEqual(einfo1[1].args, einfo2[1].args)  # almost same value
        self.assertNotEqual(exc_hash(einfo1), exc_hash(einfo2))

    def test_line_independence(self):
        try:
            self.deep_throw()
        except Exception:
            einfo1 = sys.exc_info()
        try:
            self.deep_throw()
        except Exception:
            einfo2 = sys.exc_info()
        self.assertNotEqual(einfo1, einfo2)
        self.assertEqual(exc_hash(einfo1), exc_hash(einfo2))


class TestPopValues(unittest.TestCase):
    def test_list_of_dicts(self):
        self.assertEqual(pop_values({"a": [{}, {}, {}]}), {})
        self.assertEqual(pop_values({"a": [{"q": None}, {}, {}]}), {"a": [{"q": None}]})
        self.assertEqual(
            pop_values({"a": [{}, {"q": None}, {}]}), {"a": [{}, {"q": None}]}
        )
        self.assertEqual(
            pop_values({"a": [{}, {}, {"q": None}]}), {"a": [{}, {}, {"q": None}]}
        )


if __name__ == "__main__":
    unittest.main()
