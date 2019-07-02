#!/usr/bin/env python2.7

import unittest

import canning


class TestNop(unittest.TestCase):
    def test_nop(self):
        canning.NopTeeFd.write("asdf")


class TestSlice(unittest.TestCase):
    REPORT = "20130505T065614Z-VN-AS24173-dns_consistency-no_report_id-0.1.0-probe.yaml"

    @staticmethod
    def rpt(year):
        assert year < 10000
        return "{:04d}1231T065614Z-VN-AS24173-dns_consistency-no_report_id-0.1.0-probe.yaml".format(
            year
        )

    def test_empty(self):
        asis, tarfiles = canning.pack_bucket(tuple())
        self.assertFalse(asis)
        self.assertFalse(tarfiles)

    def test_badname(self):
        self.assertRaises(RuntimeError, canning.pack_bucket, [("foo", 42)])
        self.assertRaises(
            RuntimeError, canning.pack_bucket, [("2013-05-05/" + self.REPORT, 42)]
        )

    def test_single(self):
        for sz in [0, 1, 65 * 1048576]:
            asis, tarfiles = canning.pack_bucket([(self.REPORT, sz)])
            self.assertEqual(asis, [self.REPORT])
            self.assertFalse(tarfiles)

    def test_packing(self):
        asis, tarfiles = canning.pack_bucket(
            [(self.rpt(0), 42), (self.rpt(1), 64), (self.rpt(2), 64 * 1048576)]
        )
        self.assertEqual(asis, [self.rpt(2)])
        self.assertEqual(tarfiles, {"dns_consistency.0.tar": map(self.rpt, (0, 1))})

    def test_stupid(self):  # FIXME: is it really good behaviour?...
        asis, tarfiles = canning.pack_bucket(
            [(self.rpt(0), 42), (self.rpt(1), 64 * 1048576 - 1), (self.rpt(2), 64)]
        )
        self.assertEqual(asis, map(self.rpt, (0, 1, 2)))
        self.assertEqual(tarfiles, {})


if __name__ == "__main__":
    unittest.main()
