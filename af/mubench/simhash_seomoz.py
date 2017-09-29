#!/usr/bin/env python2.7

import itertools
import re

import simhash # https://github.com/seomoz/simhash-py v0.3.0
import mmh3

WORD_RE = re.compile('''[^\t\n\x0b\x0c\r !"#$%&\'()*+,-./:;<=>?@[\\\\\\]^_`{|}~']+''')

def sim_shi4_mm3(text):
    # NB: It makes quite little sense to use both 64bit numbers to compare
    # hashes as pairwise Hamming distance using high 64bit is highly correlated
    # with the distance computed using low 64bit. It's actually expected, but
    # it means, that summing these distances is not linear and should be avoided.
    # -- https://gist.github.com/darkk/e2b2762c4fe053a3cf8a299520f0490e
    i1, i2 = itertools.tee(WORD_RE.finditer(text))
    for _ in xrange(3): # 4 words per shingle
        next(i2, None)
    mm = [mmh3.hash64(text[m1.start():m2.end()]) for m1, m2 in itertools.izip(i1, i2)]
    return (simhash.compute([_[0] & 0xffffffffffffffff for _ in mm]),
            simhash.compute([_[1] & 0xffffffffffffffff for _ in mm]))

FILE = 'warning.rt.ru.html'

# python2.7 -m timeit -v --repeat 20 --number 500 'import simhash_seomoz as b' 'b.main()'
# ~968 usec to process  10824 bytes -> 10.5 Mbytes/s # warning.rt.ru.html
# 2200 usec to process  16552 bytes ->  7.2 Mbytes/s # https://www.postgresql.org/message-id/29F36C7C98AB09499B1A209D48EAA615B7653DBCAB@mail2a.alliedtesting.com
# 2.2  msec to process 178329 bytes ->  7.7 Mbytes/s # https://stackoverflow.com/questions/1771543/postgresql-updating-an-enum-type/7834949
def main():
    TEXT = open(FILE).read()
    sim_shi4_mm3(TEXT)

if __name__ == '__main__':
    main()
