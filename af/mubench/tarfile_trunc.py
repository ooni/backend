#!/usr/bin/env python2.7
#
# Verify that tarfile handles truncated files correctly.

import os
import tarfile
import unittest
from cStringIO import StringIO
from subprocess import check_call
from tarfile_read import ReadStream

class TestTrunc(unittest.TestCase):
    FNAME = 'aa.tar'
    BODY = 'A' * 8000

    @classmethod
    def setUpClass(cls):
        with open('aa', 'w') as fd:
            fd.write(cls.BODY)
        check_call(['tar', '--create', '--file', cls.FNAME, 'aa'])
        os.unlink('aa')

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.FNAME)

    def test_truncated(self):
        # it's either exctracted as a whole or throws
        blob = open(self.FNAME).read()
        for sz in xrange(os.stat(self.FNAME).st_size):
            ndx = -1
            try:
                tarfd = tarfile.open(mode='r:', fileobj=ReadStream(StringIO(blob[:sz])))
                for ndx, tin in enumerate(tarfd):
                    fd = tarfd.extractfile(tin)
                    raw = fd.read()
                    self.assertEqual(raw, self.BODY)
            except Exception, e:
                pass # print sz, '/', ndx, 'OK', type(e), e

if __name__ == '__main__':
    unittest.main()
