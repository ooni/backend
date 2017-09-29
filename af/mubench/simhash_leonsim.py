#!/usr/bin/env python2.7

import re

import simhash # https://github.com/leonsim/simhash v1.7.1 | aka `pip install simhash=1.7.1`
import mmh3

RE_WORD = re.compile('''[^\t\n\x0b\x0c\r !"#$%&\'()*+,-./:;<=>?@[\\\\\\]^_`{|}~']+''')

TEXT = open('warning.rt.ru.html').read()
assert len(TEXT) == 10824

# python2.7 -m timeit -v --repeat 20 --number 50 'import simhash_leonsim as b' 'b.main()'
# ~21 msec to process 10824 bytes -> ~0.5 Mbytes/s
def main():
    simhash.Simhash(unicode(TEXT, 'utf-8'), reg=RE_WORD, hashfunc=lambda x: mmh3.hash64(x)[0])

if __name__ == '__main__':
    main()
