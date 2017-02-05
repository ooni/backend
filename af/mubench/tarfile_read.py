#!/usr/bin/env python2.7
#
# This mubench shows that line-by-line reading using tarfile.ExFileObject.readline()
# may be slower than reading large chunk and processing it in-place without doing
# extra string copies.
#
# Ubuntu 16.04 / Python 2.7.12 (default, Nov 19 2016, 06:48:10) / [GCC 5.4.0 20160609] on linux2
#
# Test data:
# $ lz4 -d < 2017-01-01/web_connectivity.0.tar.lz4 >web_connectivity.0.tar
# st_size = 64143360
# SHA1 = 68369072a70e0e556fa28731ca2d4b0b6a2b238b

import functools
import sys
import tarfile
import unittest
from contextlib import closing
from zlib import crc32

# $ python -m timeit --repeat 20 --setup 'from tarfile_read import main_tarpipe, main_craftpipe, nop, readblob, readlines' -- 'main_tarpipe(nop)'
# 10 loops, best of 20: 28.7 msec per loop
# -> 2130 Mbyte/s
# $ python -m timeit --repeat 20 --setup 'from tarfile_read import main_tarpipe, main_craftpipe, nop, readblob, readlines' -- 'main_craftpipe(nop)'
# 10 loops, best of 20: 12.8 msec per loop
# -> 4780 Mbyte/s
# $ python -m timeit --repeat 20 --setup 'from tarfile_read import main_tarpipe, main_craftpipe, nop, readblob, readlines' -- 'main_tarpipe(readblob)'
# 10 loops, best of 20: 113 msec per loop
# -> 540 Mbyte/s
# $ python -m timeit --repeat 20 --setup 'from tarfile_read import main_tarpipe, main_craftpipe, nop, readblob, readlines' -- 'main_craftpipe(readblob)'
# 10 loops, best of 20: 94.7 msec per loop
# -> 645 Mbyte/s
# $ python -m timeit --repeat 20 --setup 'from tarfile_read import main_tarpipe, main_craftpipe, nop, readblob, readlines' -- 'main_tarpipe(readlines)'
# 10 loops, best of 20: 360 msec per loop
# -> 170 Mbyte/s
# $ python -m timeit --repeat 20 --setup 'from tarfile_read import main_tarpipe, main_craftpipe, nop, readblob, readlines' -- 'main_craftpipe(readlines)'
# 10 loops, best of 20: 217 msec per loop
# -> 280 Mbyte/s
#
# So there are two things to note regarding memory copies & temporary buffers:
# 1. reading from hand-crafted pipe is faster than usage of tarfile battery-powered pipe
# 2. reading large blobs and slicing at exact boundaries is faster than reading line-by-line

def nop(fd):
    return -1

def readblob(fd):
    # json.loads, ujson.loads do not accept memorybuffer, they need a copy
    a = 0
    head = ''
    for blob in iter(functools.partial(fd.read, 1048576), ''):
        head = head + blob
        start = 0
        while True:
            end = head.find('\n', start)
            if end != -1:
                doc = head[start:end]
                a = crc32(doc, a)
                start = end + 1
            else:
                head = head[start:]
                break

    return a

def readlines(fd):
    a = 0
    for line in fd:
        a = crc32(line[:-1], a)
    return a

class ReadStream(object):
    def __init__(self, fileobj):
        self.__fd = fileobj
        self.__off = 0
    def tell(self):
        return self.__off
    def seek(self, dest): # NB: no `whence`
        skipwant = dest - self.__off
        if skipwant < 0:
            raise RuntimeError('Unable to seek backwards while reading the stream')
        elif skipwant > 0:
            while skipwant:
                step = min(skipwant, 32768)
                skiplen = len(self.read(step))
                if skiplen != step:
                    raise RuntimeError('Unexpected end of file', step, skiplen)
                skipwant -= step
    def read(self, *args):
        blob = self.__fd.read(*args)
        self.__off += len(blob)
        return blob

def main_craftpipe(process):
    with tarfile.open(mode='r:', fileobj=ReadStream(open('web_connectivity.0.tar'))) as tarfd:
        return main(process, tarfd)

def main_tarpipe(process):
    with tarfile.open(mode='r|', fileobj=open('web_connectivity.0.tar')) as tarfd:
        return main(process, tarfd)

def main(process, tarfd):
    var = 0
    for tin in tarfd:
        if not tin.isfile():
            raise CannerError('Non-regular file in the tar', tin.name, tin.type)
        if tin.name[-5:] == '.json':
            with closing(tarfd.extractfile(tin)) as fd:
                var += process(fd)
    return var

class TestRead(unittest.TestCase):
    def test_read(self):
        self.assertEqual(main_craftpipe(readblob), main_craftpipe(readlines))
        self.assertEqual(main_tarpipe(readblob), main_tarpipe(readlines))

if __name__ == '__main__':
    unittest.main()
