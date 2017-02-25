#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import unittest

from centrifugation import httpt_body

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


if __name__ == '__main__':
    unittest.main()
