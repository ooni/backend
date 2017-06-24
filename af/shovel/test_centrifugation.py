#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import os
import random
import string
import sys
import unittest

import psycopg2

from centrifugation import httpt_body, PGCopyFrom, pg_quote, pg_unquote, exc_hash, pop_values


def _httpt_body(body, te=None):
    d = {'body': body, 'headers': {}}
    if te is not None:
        d['headers']['TrAnSfEr-EnCoDiNg'] = te
    return httpt_body(d)

class TestChunked(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_httpt_body(''), '')
        self.assertEqual(_httpt_body('0\r\n\r\n', 'chunked'), '')

    def test_chunked(self):
        self.assertEqual(_httpt_body(
            '4\r\nasdf\r\n'
            '3\r\nqwe\r\n'
            '2\r\nzx\r\n'
            '0\r\n\r\n', 'chunked'), 'asdfqwezx')
        self.assertEqual(_httpt_body(
            u'2\r\nzx\r\n'
            u'8\r\nпсой\r\n' # NB: 8 bytes for 4 symbols!
            u'0\r\n\r\n', 'chunked'), u'zxпсой'.encode('utf-8'))

    def test_broken(self):
        raw = ('2\r\nzx\r\n'
               '7\r\nFilast\xf2\r\n'
               '0\r\n\r\n')
        self.assertEqual(_httpt_body(raw, 'chunked'), 'zxFilast\xf2')
        # NB: can't be properly de-chunked after <meta/> charset decoding
        uni = raw.decode('ISO-8859-1')
        self.assertEqual(_httpt_body(uni, 'chunked'), uni.encode('utf-8'))

class TestPGQuoting(unittest.TestCase):
    def test_bool(self):
        self.assertEqual(pg_quote(True), 'TRUE')
        self.assertEqual(pg_quote(False), 'FALSE')
    def test_bits(self):
        blob = ''.join(map(chr, xrange(256)))
        self.assertEqual(blob, pg_unquote(pg_quote(blob)))
    def test_ugly(self):
        blob = r'\\n'
        self.assertEqual(blob, pg_unquote(pg_quote(blob)))

PG = os.getenv('UNITTEST_PG')
class TestE2EQuoting(unittest.TestCase):
    # Run like that:
    # $ UNITTEST_PG='host=172.17.0.3 user=postgres' python test_centrifugation.py TestE2EQuoting
    def setUp(self):
        self.conn = psycopg2.connect(dsn=PG)
        self.table = 'tmptbl' + ''.join(random.choice(string.lowercase) for _ in xrange(6))
    def tearDown(self):
        self.conn.close()
    @unittest.skipUnless(PG, 'No PostgreSQL')
    def test_string(self):
        for mapfn in (chr, unichr):
            with self.conn, self.conn.cursor() as c:
                c.execute('CREATE TEMPORARY TABLE {} (nnn int2, ccc text) ON COMMIT DROP'.format(self.table))
                dest = PGCopyFrom(self.conn, self.table, wbufsize=64)
                for i in xrange(1, 128): # postgresql does not support \x00 in body
                    dest.write('{:d}\t{}\n'.format(i, pg_quote(mapfn(i))))
                dest.close()
                c.execute('SELECT * FROM {}'.format(self.table))
                nrows = 0
                for nnn, ccc in c:
                    self.assertEqual(nnn, ord(ccc))
                    nrows += 1
                self.assertEqual(nrows, 127)
    @unittest.skipUnless(PG, 'No PostgreSQL')
    def test_array(self):
        for mapfn in (chr, unichr):
            with self.conn, self.conn.cursor() as c:
                c.execute('CREATE TEMPORARY TABLE {} (nnn int2, ccc text[]) ON COMMIT DROP'.format(self.table))
                dest = PGCopyFrom(self.conn, self.table, wbufsize=64)
                for i in xrange(1, 128): # postgresql does not support \x00 in body
                    dest.write('{:d}\t{}\n'.format(i, pg_quote([mapfn(i), 'a', mapfn(i), 'b', mapfn(i)])))
                dest.close()
                c.execute('SELECT * FROM {}'.format(self.table))
                nrows = 0
                for nnn, ccc in c:
                    self.assertEqual(ccc, [mapfn(nnn), 'a', mapfn(nnn), 'b', mapfn(nnn)])
                    nrows += 1
                self.assertEqual(nrows, 127)

class TextExcHash(unittest.TestCase):
    def deep_throw(self):
        import socket
        socket.create_connection(('127.126.125.124', 1)) # ECONREFUSED
    def test_stack_dependence(self):
        try:
            self.deep_throw()
        except Exception:
            einfo1 = sys.exc_info()
        # NB: functools.partial does not add stack frame
        self.deep_throw = lambda fn=self.deep_throw: fn()
        try:
            self.deep_throw()
        except Exception:
            einfo2 = sys.exc_info()
        self.assertEqual(einfo1[0], einfo2[0]) # same type
        self.assertEqual(einfo1[1].args, einfo2[1].args) # almost same value
        self.assertNotEqual(exc_hash(einfo1), exc_hash(einfo2))
    def test_line_independence(self):
        try:
            self.deep_throw()
        except Exception:
            einfo1 = sys.exc_info()
        try:
            self.deep_throw()
        except Exception:
            einfo2 = sys.exc_info()
        self.assertNotEqual(einfo1, einfo2)
        self.assertEqual(exc_hash(einfo1), exc_hash(einfo2))

class TestPopValues(unittest.TestCase):
    def test_list_of_dicts(self):
        self.assertEqual(pop_values({'a': [{}, {}, {}]}), {})
        self.assertEqual(pop_values({'a': [{'q': None}, {}, {}]}), {'a': [{'q': None}]})
        self.assertEqual(pop_values({'a': [{}, {'q': None}, {}]}), {'a': [{}, {'q': None}]})
        self.assertEqual(pop_values({'a': [{}, {}, {'q': None}]}), {'a': [{}, {}, {'q': None}]})

if __name__ == '__main__':
    unittest.main()
