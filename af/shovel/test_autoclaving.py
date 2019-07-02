import os

# This is needed to make daily_workflow work
os.environ["TZ"] = "UTC"

from cStringIO import StringIO
import unittest
from operator import itemgetter

from autoclaving import stream_json_blobs, stream_yaml_blobs


def do_yaml(s):
    return map(itemgetter(1), stream_yaml_blobs(StringIO(s)))


def do_json(s):
    return map(itemgetter(1), stream_json_blobs(StringIO(s)))


class TestStreamSlicing(unittest.TestCase):
    def test_json(self):
        self.assertEqual(do_json("{foobar}\n{boobaz}\n"), ["{foobar}", "{boobaz}"])

    def test_json_truncated(self):
        blob = "{foobar}\n{boobaz}\n"
        for i in xrange(len(blob)):
            if i in (0, len(blob) / 2):
                continue  # well... can't detect that :-)
            self.assertRaises(RuntimeError, do_json, blob[:i])

    HEAD = "---\nhead...\nchopped head...\n...\n"
    FIRST = "---\nfirst...\n...\n"
    SECOND = "---\nsecond...\n...\n"

    def test_yaml(self):
        blob = self.HEAD + self.FIRST + self.SECOND
        self.assertEqual(do_yaml(blob), [self.HEAD, self.FIRST, self.SECOND])

    def test_yaml_comment(self):
        # inter-document comments are stripped by slicerr, inline comments are not
        blob = "# foo\n" "---\n" "# WAT!\n" "a: b\n" "...\n"
        self.assertEqual(do_yaml(blob), ["---\n# WAT!\na: b\n...\n"])

    def test_yaml_without_preamble(self):
        self.assertEqual(do_yaml(self.HEAD), [self.HEAD])
        with self.assertRaises(RuntimeError):
            do_yaml(self.HEAD[4:])

    def test_yaml_truncated(self):
        blob = self.HEAD + self.FIRST + self.SECOND
        for i in xrange(len(blob)):
            if i in (0, len(self.HEAD), len(self.HEAD) + len(self.FIRST)):
                continue  # well... can't detect that :-)
            self.assertRaises(RuntimeError, do_yaml, blob[:i])

    def test_yaml_empty(self):
        # tail of the 2013-05-05/20130505T065614Z-VN-AS24173-dns_consistency-no_report_id-0.1.0-probe.yaml
        blob = "---\nnull\n...\n...\n" * 5
        self.assertEqual(do_yaml(blob), ["---\nnull\n...\n"] * 5)


if __name__ == "__main__":
    unittest.main()
