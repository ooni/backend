#!/usr/bin/env python2.7
#
# This mubench shows that reading tarfile using pre-computed offsets to skip headers
# and padding may be significantly faster then parsting tarfile again and again.
#
# Ubuntu 16.04 / Python 2.7.12 (default, Nov 19 2016, 06:48:10) / [GCC 5.4.0 20160609] on linux2
#
# Test data:
# $ tar cf 2016-04-01-http_requests.tar 2016-04-01/*-http_requests-*
# 22558 files in the tar file
# st_size = 1204879360

import sys
import tarfile
import unittest
from contextlib import closing
from subprocess import Popen, PIPE
from zlib import crc32

def tarindex(fname):
    direct = []
    proc = Popen(['cat', fname], stdout=PIPE)
    with closing(proc.stdout) as rawfd, \
         tarfile.open(mode='r|', fileobj=rawfd) as tarfd:

        for tin in tarfd:
            direct.append( (tin.offset_data, tin.size) )

    return direct

# $ python -m timeit --setup 'from tarfile_seek import tarindex, tarcrc, seekcrc; fname = "2016-04-01-http_requests.tar"; index = tarindex(fname)' 'tarcrc(fname)'
# 10 loops, best of 3: 2.847 sec per loop
# -> 405 Mbyte/s
def tarcrc(fname):
    crc = []
    proc = Popen(['cat', fname], stdout=PIPE)
    with closing(proc.stdout) as rawfd, \
         tarfile.open(mode='r|', fileobj=rawfd) as tarfd:

        for tin in tarfd:
            with closing(tarfd.extractfile(tin)) as fd:
                crc.append(crc32(fd.read()))
    return crc

# $ python -m timeit --setup 'from tarfile_seek import tarindex, tarcrc, seekcrc; fname = "2016-04-01-http_requests.tar"; index = tarindex(fname)' 'seekcrc(fname, index)'
# 10 loops, best of 3: 1.323 sec per loop
# -> 870 Mbyte/s
def seekcrc(fname, ndx):
    crc = []
    proc = Popen(['cat', fname], stdout=PIPE)
    with closing(proc.stdout) as rawfd:
        offset = 0
        for off, sz in ndx:
            rawfd.read(off - offset) # no seek() for pipes
            crc.append(crc32(rawfd.read(sz)))
            offset = off + sz
    return crc

class TestSeek(unittest.TestCase):
    def test_seek(self):
        fname = '2016-04-01-http_requests.tar'
        index = tarindex(fname)
        self.assertEqual(tarcrc(fname), seekcrc(fname, index))

if __name__ == '__main__':
    unittest.main()
