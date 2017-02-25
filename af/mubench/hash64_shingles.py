#!/usr/bin/env python2.7

import re
import itertools
from hashlib import sha1

import mmh3     # mmh3=2.3.1
import xxhash   # xxhash=1.0.0

# string.whitespace + string.punctuation, it's not so smart, e.g. "I.B.M." is
# signe token in ideal world.
RE_DELIM = re.compile('''[\t\n\x0b\x0c\r !"#$%&\'()*+,-./:;<=>?@[\\\\\\]^_`{|}~']+''')

TEXT = open('warning.rt.ru.html').read()
assert len(TEXT) == 10824 and sha1(TEXT).hexdigest() == '1575ad5cc6e6db27057cd73dae6a94addfd965b2'

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
