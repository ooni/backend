#!/usr/bin/env python2.7
#
# This mubench shows pathological slowness of writing large blobs to tarfile
# in mode='w|' and a possible workaround for that slowness.
#
# Ubuntu 16.04 / Python 2.7.12 (default, Nov 19 2016, 06:48:10) / [GCC 5.4.0 20160609] on linux2

import hashlib
import os
import sys
import tarfile
import tempfile
import unittest
from contextlib import closing

def tarread(fname):
    with tarfile.open(mode='r|', fileobj=open(fname)) as tarfd:
        for tin in tarfd:
            with closing(tarfd.extractfile(tin)) as fd:
                yield tin, fd.read()

class WriteStream(object): # as tarfile._Stream write() is SLOOOW
    def __init__(self, fileobj):
        self.__fd = fileobj
        self.__off = 0
    def tell(self):
        return self.__off
    def write(self, blob):
        self.__fd.write(blob)
        self.__off += len(blob)

def process_tarfd(l, tarfd):
    for tin, blob in l:
        tin.size = len(blob)
        tarfd.addfile(tin)

        # copy-paste from tarfile.addfile
        tarfd.fileobj.write(blob)
        blocks, remainder = divmod(len(blob), tarfile.BLOCKSIZE)
        if remainder > 0:
            tarfd.fileobj.write('\0' * (tarfile.BLOCKSIZE - remainder))
            blocks += 1
        tarfd.offset += blocks * tarfile.BLOCKSIZE

TIMEIT_OUT = '/dev/shm/ooni-garbage'

# $ python -m timeit --repeat 10 --number 100 --setup 'from tarfile_write import tarread, tarwrite_fileproxy as w; l = list(tarread("web_connectivity.0.tar"))' 'w(l)'
# 100 loops, best of 10: 23.3 msec per loop
# -> 2625 Mbyte/s
def tarwrite_fileproxy(l, fdout=None):
    if fdout is None:
        fdout = open(TIMEIT_OUT, 'w')
    fdout = WriteStream(fdout)
    with tarfile.open(mode='w', fileobj=fdout) as tarfd:
        process_tarfd(l, tarfd)

# $ python -m timeit --repeat 10 --number 100 --setup 'from tarfile_write import tarread, tarwrite_file as w; l = list(tarread("web_connectivity.0.tar"))' 'w(l)'
# 100 loops, best of 10: 24 msec per loop
# -> 2550 Mbyte/s
def tarwrite_file(l, fdout=None):
    if fdout is None:
        fdout = open(TIMEIT_OUT, 'w')
    with tarfile.open(mode='w', fileobj=fdout) as tarfd:
        process_tarfd(l, tarfd)

# $ python -m timeit --setup 'from tarfile_write import tarread, tarwrite_pipe as w; l = list(tarread("web_connectivity.0.tar"))' 'w(l)'
# 10 loops, best of 3: 8.38 sec per loop
#                           ^^^ SECONDS!
# -> 7.3 Mbyte/s
def tarwrite_pipe(l, fdout=None):
    if fdout is None:
        fdout = open(TIMEIT_OUT, 'w')
    with tarfile.open(mode='w|', fileobj=fdout) as tarfd:
        process_tarfd(l, tarfd)

class TestWrite(unittest.TestCase):
    def tarwrite_sha1(self, twfn, l):
        h = hashlib.sha1()
        with tempfile.NamedTemporaryFile() as fdout:
            twfn(l, fdout)
            with open(fdout.name) as fd:
                while True:
                    blob = fd.read(1048576)
                    if not blob:
                        break
                    h.update(blob)
        return h.hexdigest()

    def test_write(self):
        fname = 'web_connectivity.0.tar'
        l = list(tarread(fname))

        shafile = self.tarwrite_sha1(tarwrite_file, l)
        shafileproxy = self.tarwrite_sha1(tarwrite_fileproxy, l)
        shapipe = self.tarwrite_sha1(tarwrite_pipe, l)

        self.assertEqual(shafile, shafileproxy)
        self.assertEqual(shafile, shapipe)

if __name__ == '__main__':
    unittest.main()
