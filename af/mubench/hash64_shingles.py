#!/usr/bin/env python2.7

import re
import itertools
import struct
from hashlib import sha1
from hashlib import md5

import mmh3     # mmh3=2.5.1
import xxhash   # xxhash=1.3.0
import simhash  # simhash-py==0.4.0

# string.whitespace + string.punctuation, it's not so smart, e.g. "I.B.M." is
# signe token in ideal world.
RE_DELIM = re.compile('''[\t\n\x0b\x0c\r !"#$%&\'()*+,-./:;<=>?@[\\\\\\]^_`{|}~']+''')

TEXT = open('warning.rt.ru.html').read()
assert len(TEXT) == 10824 and sha1(TEXT).hexdigest() == '1575ad5cc6e6db27057cd73dae6a94addfd965b2'

def prepare():
    i1, i2 = itertools.tee(RE_DELIM.finditer(TEXT))
    for i in xrange(4):
        next(i2, None)
    return itertools.izip(i1, i2) # iterator over beginning and the end of the shingle

def baseline(): # 1000 loops, best of 50: 268 usec per loop
    for m1, m2 in prepare():
        pass

def baseline_str(): # 100 loops, best of 100: 430 usec per loop
    for m1, m2 in prepare():
        i = TEXT[m1.end():m2.start()]

def baseline_hash_u64(): # 100 loops, best of 100: 568 usec per loop
    for m1, m2 in prepare():
        i = hash(TEXT[m1.end():m2.start()]) & 0xFFFFFFFFFFFFFFFF

def simhash_u64(): # 100 loops, best of 100: 1.39 msec per loop
    unsigned_hash = simhash.unsigned_hash
    for m1, m2 in prepare():
        i = unsigned_hash(TEXT[m1.end():m2.start()])

def simhash_md5_u64(): # 100 loops, best of 100: 1.47 msec per loop
    for m1, m2 in prepare():
        digest = md5(TEXT[m1.end():m2.start()]).digest()[0:8]
        i = struct.unpack('>Q', digest)[0] & 0xFFFFFFFFFFFFFFFF

def sha1_u64(): # 100 loops, best of 100: 1.41 msec per loop
    for m1, m2 in prepare():
        digest = sha1(TEXT[m1.end():m2.start()]).digest()[0:8]
        i = struct.unpack('>Q', digest)[0] & 0xFFFFFFFFFFFFFFFF

def sha1_u64_v1(): # 100 loops, best of 100: 1.29 msec per loop
    unpacker = struct.Struct('>Q')
    for m1, m2 in prepare():
        digest = sha1(TEXT[m1.end():m2.start()]).digest()[0:8]
        i = unpacker.unpack(digest)[0]

def sha1_u64_v2(): # 100 loops, best of 100: 1.35 msec per loop
    unpacker = struct.Struct('>Q')
    for m1, m2 in prepare():
        digest = sha1(TEXT[m1.end():m2.start()]).digest()
        i = unpacker.unpack_from(digest)[0]

def mmh3_u64_v1(): # 100 loops, best of 100: 880 usec per loop
    for m1, m2 in prepare():
        i = mmh3.hash64(TEXT[m1.end():m2.start()], signed=False)[0]

def mmh3_u64_v2(): # 100 loops, best of 100: 715 usec per loop
    for m1, m2 in prepare():
        i = mmh3.hash64(TEXT[m1.end():m2.start()], 0, True, False)[0]

def mmh3_u64_v3(): # 100 loops, best of 100: 690 usec per loop
    for m1, m2 in prepare():
        i = mmh3.hash64(TEXT[m1.end():m2.start()])[0] & 0xFFFFFFFFFFFFFFFF

def mmh3_u64_v4(): # 100 loops, best of 100: 661 usec per loop
    hash64 = mmh3.hash64
    for m1, m2 in prepare():
        i = hash64(TEXT[m1.end():m2.start()])[0] & 0xFFFFFFFFFFFFFFFF

def xxhash_u64_v1(): # 100 loops, best of 100: 700 usec per loop
    for m1, m2 in prepare():
        i = xxhash.xxh64_intdigest(TEXT[m1.end():m2.start()])

def xxhash_u64_v2(): # 100 loops, best of 100: 676 usec per loop
    xxh64_intdigest = xxhash.xxh64_intdigest
    for m1, m2 in prepare():
        i = xxh64_intdigest(TEXT[m1.end():m2.start()])

########################################################################
# Following are historical numbers for mmh3=2.3.1 xxhash=1.0.0

# python2.7 -m timeit -v --repeat 20 --number 500 'import bench as b' 'b.main()'
def main():
    i1, i2 = itertools.tee(RE_DELIM.finditer(TEXT))
    for i in xrange(4):
        next(i2, None)
    for m1, m2 in itertools.izip(i1, i2):
        pass                                                        #  286 usec per loop
        #TEXT[m1.end():m2.start()]                                  #  434 usec
        #memoryview(TEXT)[m1.end():m2.start()]                      #  658 usec <- WTF?
        #buffer(TEXT, m1.end(), m2.start() - m1.end())              #  618 usec <- WTF?
        #mmh3.hash64(TEXT[m1.end():m2.start()])                     #  610 usec
        #mmh3.hash64(buffer(TEXT, m1.end(), m2.start() - m1.end())) #  823 usec <- WTF?
        #xxhash.xxh64(TEXT[m1.end():m2.start()])                    #  668 usec
        #sha1(TEXT[m1.end():m2.start()])                            #  843 usec
        #sha1(memoryview(TEXT)[m1.end():m2.start()])                # 1130 usec
        #sha1(buffer(TEXT, m1.end(), m2.start() - m1.end()))        # 1105 usec

if __name__ == '__main__':
    main()
