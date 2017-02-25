#!/usr/bin/env python2.7

import itertools
import re

import simhash # https://github.com/seomoz/simhash-py v0.3.0
import mmh3

RE_WORD = re.compile('''[^\t\n\x0b\x0c\r !"#$%&\'()*+,-./:;<=>?@[\\\\\\]^_`{|}~']+''')

TEXT = open('warning.rt.ru.html').read()
assert len(TEXT) == 10824

# python2.7 -m timeit -v --repeat 20 --number 500 'import simhash_seomoz as b' 'b.main()'
# ~968 usec to process 10824 bytes -> ~10.5 Mbytes/s
def main():
    i1, i2 = itertools.tee(RE_WORD.finditer(TEXT))
    for i in xrange(3):
        next(i2, None)
    mm = [mmh3.hash64(TEXT[m1.start():m2.end()]) for m1, m2 in itertools.izip(i1, i2)]
    simhash.compute([_[0] & 0xffffffffffffffff for _ in mm])
    simhash.compute([_[1] & 0xffffffffffffffff for _ in mm])

if __name__ == '__main__':
    main()
