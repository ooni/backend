#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import argparse
import collections
import functools
import gzip
import hashlib
import itertools
import numbers
import os
import re
import sys
import traceback
from base64 import b64decode
from contextlib import closing
from cStringIO import StringIO
from datetime import timedelta
from itertools import groupby
from operator import itemgetter

import lz4.frame as lz4frame
import mmh3
import psycopg2
import simhash
import ujson

import autoclaving
from canning import ChecksummingTee, NopTeeFd, isomidnight, dirname
from tor_log import parse_tor_log

# It does NOT take into account metadata tables right now:
# - autoclaved: it's not obvious if anything can be updated there
# - report & measurement: have significant amount of metadata and may be actually updated eventually
# Technically `http_headers` was added after CODE_VER=3, but bad headers were
# causing bucket-wide exception, so re-import is not forced.
CODE_VER = 4

CODE_VER_REPROCESS = 0 # special `code_ver` value to do partial re-processing

FLAG_TRUE_TEMP = True # keep temporary tables if the flag is false
FLAG_DEBUG_CHAOS = False # random fault injection
FLAG_FAIL_FAST = False
FLAG_SKIP_SIMHASH = True # it takes 75% of time, disable it for a while 
assert not (FLAG_DEBUG_CHAOS and FLAG_FAIL_FAST), 'Absurd!'

if FLAG_DEBUG_CHAOS:
    import random

# There are some reports that have duplicate report_id, same filename and same
# content, there are ~500 of them by 2017-07-12. Some of them should be skipped.
DUPLICATE_REPORTS = set()

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
    # mmh3.hash64 produces pairs of signed i64
    # simhash.compute expects list of unsigned ui64 and produces unsigned ui64
    mm = [mmh3.hash64(text[m1.start():m2.end()]) for m1, m2 in itertools.izip(i1, i2)]
    return (simhash.compute([_[0] & 0xffffffffffffffff for _ in mm]),
            simhash.compute([_[1] & 0xffffffffffffffff for _ in mm]))

# NB: 30% of simtext2pg.py is spent here
def to_signed(integer):
    '''Convert an unsigned integer into a signed integer with the same bits'''
    return integer - 0x10000000000000000 if integer > 0x7fffffffffffffff else integer

def from_signed(integer):
    '''Convert an unsigned integer into a signed integer with the same bits'''
    return integer & 0xffffffffffffffff if integer < 0 else integer

def to_signed32(integer):
    '''Convert an unsigned integer into a signed integer with the same bits'''
    return integer - 0x100000000 if integer > 0x7fffffff else integer

def from_signed32(integer):
    '''Convert an unsigned integer into a signed integer with the same bits'''
    return integer & 0xffffffff if integer < 0 else integer

# Tiny error in code (e.g. if it's gets some optimisation) may screw database,
# so the check is done on every launch.
assert from_signed((-2)**63) == 2**63
assert from_signed(-1) == 2**64-1
for i in (0, 2**62, 2**63-1, 2**63, 2**63+1, 2**64-1):
    assert from_signed(to_signed(i)) == i
for i in (-2**63, -2**62, -1, 0, 1, 2**63-1):
    assert to_signed(from_signed(i)) == i

CHUNK_RE = re.compile('\x0d\x0a([0-9a-f]+)\x0d\x0a')

def httpt_body(response):
    if response is None:
        return None
    body = response['body']
    if body is None:
        return None
    if isinstance(body, dict):
        assert body.viewkeys() == {'data', 'format'} and body['format'] == 'base64'
        body = b64decode(body['data'])
    if isinstance(body, unicode):
        body = body.encode('utf-8')
    if body == '0\r\n\r\n':
        return ''
    if body[-7:] == '\r\n0\r\n\r\n': # looks like chunked
        # NB: chunked blobs MAY be broken as ...
        # - \0 bytes were stripped from binary body
        # - unicode was enforced using <meta/> charset encoding
        for k, v in response['headers'].iteritems():
            if k.lower() == 'transfer-encoding' and v.lower() == 'chunked':
                break
        else:
            # that's bad to throw:
            # - control measurement from shows partial body https://explorer.ooni.torproject.org/measurement/xLa7pgssTf9GRA6b3KZqJNyXFHXvZeB7XwxH9iAsuLsq4hGD27vXtgqnRKIJXyWO?input=http:%2F%2Fwww.radioislam.org
            # - that also happens "for real" https://explorer.ooni.torproject.org/measurement/20160715T020111Z_AS27775_kUa9SzwloGExQliV9qg8QHJBv20UTNgaVDb1mGG22XTH2N4J4y?input=http:%2F%2Fakwa.ru
            raise RuntimeError('Chunked body without `Transfer-Encoding: chunked`', response['headers'])
        out = []
        offset = body.index('\r')
        bloblen = int(body[0:offset], 16)
        assert body[offset:offset+2] == '\r\n'
        offset += 2
        while True:
            out.append(body[offset:offset+bloblen])
            if not bloblen:
                assert body[offset:] == '\r\n'
                break
            offset += bloblen
            m = CHUNK_RE.match(buffer(body, offset))
            if not m:
                return body # broken chunking :-/
            offset += m.end() - m.start()
            bloblen = int(m.group(1), 16)
        return ''.join(out)
    return body

def http_status_code(code):
    if code is None or 100 <= code <= 999:
        return code
    else:
        raise RuntimeError('Invalid HTTP code', code)

def http_headers(headers):
    # make headers dict friendly to postgres
    return {pg_uniquote(k): pg_uniquote(v) for k, v in headers.iteritems()}

def dns_ttl(ttl):
    # RFC1035 states: positive values of a signed 32 bit number
    if ttl is None or 0 < ttl <= 0x7fffffff:
        return ttl
    else:
        raise RuntimeError('Invalid DNS TTL', ttl)

########################################################################

PG_ARRAY_SPECIAL_RE = re.compile('[\t\x0a\x0b\x0c\x0d {},"\\\\]')
BAD_UTF8_RE = re.compile( # https://stackoverflow.com/questions/18673213/detect-remove-unpaired-surrogate-character-in-python-2-gtk
    ur'''(?x)            # verbose expression (allows comments)
    (                    # begin group
    [\ud800-\udbff]      #   match leading surrogate
    (?![\udc00-\udfff])  #   but only if not followed by trailing surrogate
    )                    # end group
    |                    #  OR
    (                    # begin group
    (?<![\ud800-\udbff]) #   if not preceded by leading surrogate
    [\udc00-\udfff]      #   match trailing surrogate
    )                    # end group
    |                    #  OR
    \u0000
    ''')

def pg_uniquote(s):
    if isinstance(s, str):
        s = unicode(s, 'utf-8')
    assert isinstance(s, unicode)
    return BAD_UTF8_RE.sub(u'\ufffd', s) # `re` is smart enough to return same object in case of no-op

def pg_quote(s):
    # The following characters must be preceded by a backslash if they
    # appear as part of a column value: backslash itself, newline, carriage
    # return, and the current delimiter character.
    # -- https://www.postgresql.org/docs/9.6/static/sql-copy.html
    if isinstance(s, basestring):
        # postgres requires UTF8, it's also unhappy about
        # - unpaired surrogates https://www.postgresql.org/message-id/20060526134833.GC27513%40svana.org
        #   example at 2016-04-01/http_requests.06.tar.lz4 | grep myfiona.co.kr
        # - \u0000 as in ``DETAIL:  \u0000 cannot be converted to text.``
        #   example at https://github.com/TheTorProject/ooni-pipeline/issues/65
        if isinstance(s, str):
            s = unicode(s, 'utf-8')
        s = BAD_UTF8_RE.sub(u'\ufffd', s).encode('utf-8')
        return s.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    elif s is None:
        return '\\N'
    elif isinstance(s, bool): # WTF: assert isinstance(True, numbers.Number)!
        return 'TRUE' if s else 'FALSE'
    elif isinstance(s, numbers.Number):
        return s
    elif isinstance(s, list):
        if all(isinstance(el, basestring) for el in s):
            escaped = []
            for el in s:
                if PG_ARRAY_SPECIAL_RE.search(el):
                    escaped.append('"' + el.replace('\\', '\\\\').replace('"', '\\"') + '"') # 8-[ ~ ]
                else:
                    escaped.append(el)
            return pg_quote('{' + ','.join(escaped) + '}') # yes, once more!
        elif all(isinstance(el, numbers.Number) for el in s):
            return '{' + ','.join(map(str, s)) + '}'
        else:
            raise RuntimeError('Unable to quote list of unknown type', s)
    else:
        raise RuntimeError('Unable to quote unknown type', s)

def pg_binquote(s):
    assert isinstance(s, str)
    return '\\\\x' + s.encode('hex')

def pg_unquote(s):
    if not isinstance(s, basestring):
        raise RuntimeError('Unable to quote unknown type', s)
    if s != '\\N':
        return s.decode('string_escape') # XXX: gone in Python3
    else:
        return None

class PGCopyFrom(object):
    # Write buffer for COPY command to be able to COPY to several
    # output tables over single postgres session. Alternative is to use several
    # sessions and pipe data across threads with significant CPU overhead and
    # inability to process every OONI measurement using set of functions to
    # have clean "residual" document after data extraction.
    def __init__(self, pgconn, table, badsink=None, wbufsize=2097152, **kwargs):
        # default chunk size is taken as approx. cwnd between production VMs
        self.__pgconn = pgconn
        self.__table = table
        self.__badsink = badsink
        self.flush = self.__flush_easygoing if badsink is None else self.__flush_stubborn
        self.__wbufsize = wbufsize
        self.__kwargs = kwargs
        self.__buf = StringIO()
    def write(self, line):
        assert len(line) == 0 or line[-1] == '\n'
        pos = self.__buf.tell()
        if pos > 0 and pos + len(line) > self.__wbufsize:
            self.flush()
        self.__buf.write(line)
    def __flush_easygoing(self):
        self.__buf.reset()
        with self.__pgconn.cursor() as c:
            c.copy_from(self.__buf, self.__table, **self.__kwargs)
        self.__buf.reset()
        self.__buf.truncate()
    def __flush_stubborn(self):
        self.__buf.seek(0, os.SEEK_END)
        buf_size = self.__buf.tell()
        bad_lines = []
        base_line = 0
        start_pos = 0
        bad_size = 0
        good_size = 0
        eols = None
        with self.__pgconn.cursor() as c:
            while start_pos < buf_size:
                self.__buf.seek(start_pos)
                c.execute('SAVEPOINT flush_stubborn')
                try:
                    c.copy_from(self.__buf, self.__table, **self.__kwargs)
                except (psycopg2.DataError, psycopg2.IntegrityError) as exc:
                    m = re.search(r'\bCOPY {}, line (\d+)'.format(self.__table), exc.diag.context)
                    if m is not None: # yes, it's best possible way to extract that datum :-(
                        line = int(m.group(1)) - 1
                        assert line >= 0
                        line += base_line
                        c.execute('ROLLBACK TO SAVEPOINT flush_stubborn')
                    else:
                        raise
                else:
                    line = None
                c.execute('RELEASE SAVEPOINT flush_stubborn') # NB: ROLLBACK does not RELEASE, https://www.postgresql.org/message-id/1354145331.1766.84.camel%40sussancws0025
                if line is None:
                    self.__buf.truncate(start_pos)
                    good_size += buf_size - start_pos
                    start_pos = buf_size # to break the loop
                else:
                    if eols is None: # delay computation till error
                        eols = list(m.end() for m in re.finditer('\n', self.__buf.getvalue()))
                    start = eols[line-1] if line > 0 else 0
                    end = eols[line]
                    if bad_lines and bad_lines[-1][1] == start:
                        start, _ = bad_lines.pop() # merge consequent bad lines
                    bad_lines.append((start, end))
                    assert end > start_pos
                    start_pos = end
                    base_line = line + 1
            # __buf is either empty or ends with some bad lines now
            if bad_lines:
                for start, end in bad_lines:
                    self.__buf.seek(start)
                    bad = self.__buf.read(end - start)
                    assert len(bad) == end - start
                    self.__badsink.write(BadrowFeeder.badrow_row(self.__table, bad))
                    bad_size += len(bad)
                good_buf = StringIO()
                # transforming bad_lines to good_lines
                good_lines = list(sum(bad_lines, ()))
                if good_lines[0] == 0: # first blob was bad
                    good_lines.pop(0)
                else: # first blob was good
                    good_lines.insert(0, 0)
                good_lines.pop() # last blob is always bad :)
                for start, end in zip(good_lines[::2], good_lines[1::2]):
                    self.__buf.seek(start)
                    good_buf.write(self.__buf.read(end - start))
                good_size += good_buf.tell()
                if good_buf.tell():
                    self.__buf = good_buf
                    self.__flush_easygoing()
                else:
                    self.__buf.truncate(0)
            assert good_size + bad_size == buf_size
        assert self.__buf.tell() == 0
    def close(self):
        self.flush()
        self.__buf.close()
    @property
    def closed(self):
        return self.__buf.closed

def load_autoclaved_index(autoclaved_index):
    # Returns: {filename: file_sha1 for autoclaved}
    files = {}
    with gzip.GzipFile(autoclaved_index, 'r') as indexfd:
        for _, doc in autoclaving.stream_json_blobs(indexfd):
            if 'file"' not in doc: # fast-path to avoid parsing 99.9% lines
                continue
            doc = ujson.loads(doc)
            if doc['type'] == 'file':
                filename = doc['filename']
            elif doc['type'] == '/file':
                files[filename] = b64decode(doc['file_sha1'])
    return files

def load_autoclaved_db_todo(pgconn, files, bucket):
    # Returns: {files to ingest}, {files to re-ingest}, {files to re-process}
    #   ingest    ~ create new measurement records
    #   reingest  ~ preserve measurement `msm_no`, update binary representation of autoclaved file & re-parse data
    #   reprocess ~ just re-parse data (or some sub-set of tables)
    files = files.copy() # shallow copy to pop values from
    reingest, reprocess = set(), set()
    with pgconn.cursor() as c:
        c.execute('SELECT filename, file_sha1, code_ver FROM autoclaved WHERE bucket_date = %s', (bucket,))
        for filename, file_sha1, code_ver in c:
            file_sha1 = str(file_sha1) # file_sha1 is returned as buffer()
            if filename not in files:
                raise RuntimeError('Unknown filename in autoclaved PG table present in autoclaved/index.json.gz', filename)
            elif files[filename] != file_sha1: # autoclaved file changed, e.g. PII cleanup
                reingest.add(filename)
            elif code_ver < CODE_VER: # including CODE_VER_REPROCESS that is less than any CODE_VER
                reprocess.add(filename)
            elif code_ver == CODE_VER:
                pass # no-op
            else: # including code_ver > CODE_VER
                raise RuntimeError('Bad autoclaved row', filename, file_sha1, code_ver)
            files.pop(filename)
    ingest = files.viewkeys() # files that are not in the database at all
    return ingest, reingest, reprocess

def create_temp_table(pgconn, table, definition):
    # XXX: never ever use user-supplied `new_table` and `tpl_table` :-)
    if FLAG_TRUE_TEMP:
        create_table = 'CREATE TEMPORARY TABLE {table} ({definition}) ON COMMIT DROP'
    else:
        create_table = 'CREATE TABLE {table} ({definition})'
    with pgconn.cursor() as c:
        c.execute(create_table.format(table=table, definition=definition))

def copy_meta_from_index(pgconn, ingest, reingest, autoclaved_index, bucket):
    # Writing directly to `report` table is impossible as part of `report`
    # table is parsed from data files, same is true for `measurement` table.
    # The reason for `autoclaved` is cross-reference generation, it's possible
    # to avoid it, but the price is useless extra complexity. Filling these
    # three tables one-by-one is also possible, but it makes re-ingestion
    # preserving `*_no` sequence values and available range a more complex task
    # as sequence is non-transactional.
    if not DUPLICATE_REPORTS:
        # FIXME: eventually this assertion should be removed (if DUPLICATE_REPORTS
        # grows to voluminous list) and replaced with some smarter code.
        raise RuntimeError('Empty DUPLICATE_REPORTS')
    # NB: `autoclaved_meta` has no `code_ver` and `bucket_date`
    create_temp_table(pgconn, 'autoclaved_meta', '''
        autoclaved_no   integer DEFAULT nextval('autoclaved_no_seq') NOT NULL,
        autoclaved_xref integer NOT NULL,
        filename        text    NOT NULL,
        reingest        boolean NOT NULL,
        file_size       size4   NOT NULL,
        file_crc32      integer NOT NULL,
        file_sha1       sha1    NOT NULL
    ''')
    create_temp_table(pgconn, 'report_meta', '''
        report_no       integer DEFAULT nextval('report_no_seq') NOT NULL,
        report_xref     integer NOT NULL,
        autoclaved_no   integer NOT NULL,
        autoclaved_xref integer NOT NULL,
        badtail         size4,
        textname        text    NOT NULL,
        orig_sha1       sha1    NOT NULL
    ''')
    create_temp_table(pgconn, 'measurement_meta', '''
        msm_no      integer DEFAULT nextval('msm_no_seq') NOT NULL,
        report_no   integer NOT NULL,
        report_xref integer NOT NULL,
        frame_off   size4   NOT NULL,
        frame_size  size4   NOT NULL,
        intra_off   size4   NOT NULL,
        intra_size  size4   NOT NULL,
        orig_sha1   sha1    NOT NULL
    ''')
    if not ingest and not reingest: # short-cut
        return
    autoclaved_columns = ('autoclaved_no', 'autoclaved_xref', 'filename', 'reingest',
                          'file_size', 'file_crc32', 'file_sha1')
    report_columns = ('report_no', 'report_xref', 'autoclaved_no', 'autoclaved_xref',
                      'badtail', 'textname', 'orig_sha1')
    measurement_columns = ('msm_no', 'report_no', 'report_xref', 'frame_off', 'frame_size',
                           'intra_off', 'intra_size', 'orig_sha1')
    autoclaved_xref_seq = itertools.count(1000000000) # actual value does not matter, that's just DBG
    report_xref_seq = itertools.count(1000000000)
    # Another possible implementation may have single wbuf per table, but it
    # needs some placeholder value in `*_no` column that is UPDATEd with
    # nextval(). That's ± same complexity, but twice as more tuple writes for
    # ingestion of new data as postgres has no in-place update.
    dest_wbuf = {
        ('/file', 'new'):   PGCopyFrom(pgconn, 'autoclaved_meta', columns=autoclaved_columns[1:]),
        ('/file', 're'):    PGCopyFrom(pgconn, 'autoclaved_meta', columns=autoclaved_columns),
        ('/report', 'new'): PGCopyFrom(pgconn, 'report_meta', columns=report_columns[1:]),
        ('/report', 're'):  PGCopyFrom(pgconn, 'report_meta', columns=report_columns),
        ('datum', 'new'):   PGCopyFrom(pgconn, 'measurement_meta', columns=measurement_columns[1:]),
        ('datum', 're'):    PGCopyFrom(pgconn, 'measurement_meta', columns=measurement_columns),
    }
    def write_row(atclv_filename, doc_type, copy_row):
        if atclv_filename in ingest:
            key = 'new'
        elif atclv_filename in reingest:
            key = 're'
            copy_row = '0\t' + copy_row
        else:
            raise AssertionError('BUG: should never happen')
        dest_wbuf[(doc_type, key)].write(copy_row)
    with gzip.GzipFile(autoclaved_index, 'r') as indexfd:
        atclv, rpt, frm = None, None, None # carry corresponding doc
        autoclaved_xref, report_xref = None, None # act as "should-process" flag as well
        for _, doc in autoclaving.stream_json_blobs(indexfd):
            doc = ujson.loads(doc)
            t = doc['type']
            if t == 'file': # autoclaved file
                if atclv is not None:
                    raise RuntimeError('Corrupt index file', autoclaved_index, doc)
                atclv = doc
                if atclv['filename'] in ingest or atclv['filename'] in reingest:
                    autoclaved_xref = next(autoclaved_xref_seq)
            elif t == '/file':
                if atclv is None:
                    raise RuntimeError('Corrupt index file', autoclaved_index, doc)
                if autoclaved_xref is not None:
                    write_row(atclv['filename'], t, '{:d}\t{}\t{}\t{:d}\t{:d}\t{}\n'.format(
                        autoclaved_xref,
                        pg_quote(atclv['filename']),
                        pg_quote(atclv['filename'] in reingest),
                        doc['file_size'],
                        doc['file_crc32'],
                        pg_binquote(b64decode(doc['file_sha1']))))
                atclv, autoclaved_xref = None, None
            elif t == 'report':
                if atclv is None or rpt is not None or report_xref is not None:
                    raise RuntimeError('Corrupt index file', autoclaved_index, doc)
                rpt = doc
                if autoclaved_xref is not None and rpt['textname'] not in DUPLICATE_REPORTS:
                    report_xref = next(report_xref_seq)
            elif t == '/report':
                if atclv is None or rpt is None:
                    raise RuntimeError('Corrupt index file', autoclaved_index, doc)
                if autoclaved_xref is not None and report_xref is not None:
                    write_row(atclv['filename'], t, '{:d}\t0\t{:d}\t{}\t{}\t{}\n'.format(
                        report_xref,
                        autoclaved_xref,
                        pg_quote(doc.get('src_cutoff')), # nullable
                        pg_quote(rpt['textname']),
                        pg_binquote(b64decode(rpt['orig_sha1']))))
                rpt, report_xref = None, None
            elif t == 'frame':
                if frm is not None:
                    raise RuntimeError('Corrupt index file', autoclaved_index, doc)
                frm = doc # there is `text_size` as well, but that's not that useful
            elif t == '/frame':
                if frm is None:
                    raise RuntimeError('Corrupt index file', autoclaved_index, doc)
                frm = None
            elif t == 'datum':
                if atclv is None or rpt is None:
                    raise RuntimeError('Corrupt index file', autoclaved_index, doc)
                if autoclaved_xref is not None and report_xref is not None:
                    write_row(atclv['filename'], t, '0\t{:d}\t{:d}\t{:d}\t{:d}\t{:d}\t{}\n'.format(
                        report_xref,
                        frm['file_off'],
                        frm['file_size'],
                        doc['text_off'] - frm['text_off'], # intra-frame off, as text_off is absolute
                        doc['text_size'], # intra-frame size equals to stream size :)
                        pg_binquote(b64decode(doc['orig_sha1']))))
            else:
                raise RuntimeError('Unknown index.json.gz row type', autoclaved_index, doc)
    # `dest_wbuf` is not managed with closing() to avoid masking one exception
    # with another in case of failure.
    for wbuf in dest_wbuf.itervalues():
        wbuf.close()
    with pgconn.cursor() as c:
        c.execute('''UPDATE autoclaved_meta AS meta SET autoclaved_no = atclv.autoclaved_no
             FROM autoclaved AS atclv
            WHERE meta.autoclaved_no = 0
              AND atclv.bucket_date = %s
              AND meta.filename = atclv.filename
        ''', [bucket]) # reingest
        c.execute('''UPDATE report_meta AS meta SET autoclaved_no = atclv.autoclaved_no
            FROM autoclaved_meta AS atclv
            WHERE atclv.autoclaved_xref = meta.autoclaved_xref
        ''') # every row
        c.execute('''UPDATE report_meta AS meta SET report_no = rpt.report_no
            FROM autoclaved AS atclv, report AS rpt
            WHERE meta.report_no = 0
              AND meta.autoclaved_no = rpt.autoclaved_no
              AND meta.textname = rpt.textname
              AND meta.orig_sha1 = rpt.orig_sha1
        ''') # reingest
        c.execute('''UPDATE measurement_meta AS meta SET report_no = rpt.report_no
            FROM report_meta AS rpt
            WHERE meta.report_xref = rpt.report_xref
        ''') # every row
        # First, `orig_sha1` match is not enough to match two duplicate measurements
        # within same report, but order within report file should be enough.
        # Second, `orig_sha1` destiny is unclear. Maybe it should be eventually
        # dropped as it's also information leak. Think of bruteforcing MSISDN...
        c.execute('''UPDATE measurement_meta AS meta SET msm_no = msm.msm_no
            FROM (
                SELECT
                    msm_no,
                    report_no,
                    row_number() OVER (PARTITION BY report_no ORDER BY frame_off, intra_off) AS _rno,
                    orig_sha1
                FROM measurement
                WHERE report_no IN (SELECT DISTINCT report_no FROM measurement_meta WHERE msm_no = 0)
            ) AS msm, (
                SELECT
                    report_no,
                    row_number() OVER (PARTITION BY report_no ORDER BY frame_off, intra_off) AS _rno,
                    frame_off,
                    intra_off,
                    orig_sha1
                FROM measurement_meta
                WHERE msm_no = 0
            ) AS metarno
            WHERE meta.msm_no = 0
              AND meta.report_no = metarno.report_no AND meta.report_no = msm.report_no
              AND metarno._rno = msm._rno
              AND meta.orig_sha1 = metarno.orig_sha1 AND meta.orig_sha1 = msm.orig_sha1
              AND meta.frame_off = metarno.frame_off
              AND meta.intra_off = metarno.intra_off
        ''') # reingest
        # and a usual safety net :-)
        c.execute('''
            SELECT 'atclv', COUNT(*) FROM autoclaved_meta WHERE autoclaved_no = 0
            UNION ALL
            SELECT 'rpt', COUNT(*) FROM report_meta WHERE report_no = 0
            UNION ALL
            SELECT 'msm', COUNT(*) FROM measurement_meta WHERE msm_no = 0
        ''')
        stat = dict(c)
        if stat != {'atclv': 0, 'rpt': 0, 'msm': 0}:
            raise RuntimeError('Unable to preserve rows properly while re-ingesting', bucket, stat)

def load_global_duplicate_reports(pgconn):
    with pgconn.cursor() as c:
        c.execute('SELECT textname FROM repeated_report WHERE NOT used')
        DUPLICATE_REPORTS.update(_[0] for _ in c)

def delete_data_to_reprocess(pgconn, bucket):
    # Evreything in *_meta is either ingested from scratch or re-ingested.
    # Some other rows in SOME tables (depending on code_ver) should also be deleted.
    with pgconn.cursor() as c:
        # Following queries are done like that as reingest is rare, so that's usually no-op.
        # `WITH ... SELECT` is used due to syntax limitation, plain `CREATE ... AS DELETE`
        # or `WITH del CREATE ... AS TABLE del` do not work :(
        c.execute('''
        CREATE TEMPORARY TABLE del_atclv AS
        WITH del AS (
            DELETE FROM autoclaved WHERE autoclaved_no IN (
                SELECT autoclaved_no FROM autoclaved_meta WHERE reingest)
            RETURNING autoclaved_no
        ) SELECT * FROM del;

        CREATE TEMPORARY TABLE del_rpt AS
        WITH del AS (
            DELETE FROM report WHERE autoclaved_no IN (SELECT autoclaved_no FROM del_atclv)
            RETURNING report_no
        ) SELECT * FROM del;

        CREATE TEMPORARY TABLE del_msm AS
        WITH del AS (
            DELETE FROM measurement WHERE report_no IN (SELECT report_no FROM del_rpt)
            RETURNING msm_no
        ) SELECT * FROM del;

        DROP TABLE del_atclv, del_rpt;

        SELECT 1 FROM del_msm LIMIT 1
        ''')
        # TODO: delete some tables that are not DATA_TABLES
        # CODE_VER_REPROCESS is not distinguishable from code_ver=NULL in terms of DATA_TABLES
        # Right now `code_ver` represents tables to be cleaned up based on
        # `del_msm` due to `reingest` action, it does NOT represent new files
        # to be ingested.
        code_ver = set() if len(list(c)) == 0 else {CODE_VER_REPROCESS}
        # `code_ver` is updated with all known versions of the bucket.
        c.execute('SELECT DISTINCT code_ver FROM autoclaved WHERE bucket_date = %s', [bucket])
        code_ver.update(_[0] for _ in c)
        code_ver = sorted(code_ver)
        for ver, next_ver in zip(code_ver, code_ver[1:] + [CODE_VER]):
            if 0 <= ver < CODE_VER: # NULL is already at `del_msm`, CODE_VER never requires cleanup
                # `del_msm` is updated to include measurements for `reprocess` action.
                c.execute('''INSERT INTO del_msm SELECT msm_no
                    FROM autoclaved
                    JOIN report USING (autoclaved_no)
                    JOIN measurement USING (report_no)
                    WHERE bucket_date = %s AND code_ver = %s
                ''', [bucket, ver])
            elif ver < 0 or CODE_VER < ver:
                raise RuntimeError('Invalid `code_ver` in DB', ver)
            for tbl in DATA_TABLES:
                # every table should be cleaned only once to minimise number of queries
                should_be_cleaned = ver < tbl.min_compat_code_ver
                should_be_cleaned_now = tbl.min_compat_code_ver <= next_ver
                if should_be_cleaned and should_be_cleaned_now:
                    c.execute('DELETE FROM {} WHERE msm_no IN (SELECT msm_no FROM del_msm)'.format(tbl.data_table))
                    print 'DELETE FROM {} because of ver={:d} ~ {:d} rows gone'.format(tbl.data_table, ver, c.rowcount)
        c.execute('DROP TABLE del_msm')
        # when DATA_TABLES cleanup is done, CODE_VER_REPROCESS is added to handle files to `ingest`
        c.execute('SELECT 1 FROM autoclaved_meta WHERE NOT reingest LIMIT 1')
        code_ver = set(code_ver)
        if len(list(c)) == 1:
            # it should be actually None/NULL, but CODE_VER_REPROCESS
            # simplifies version arithmetics in prepare_destination()
            code_ver.add(CODE_VER_REPROCESS)
    assert None not in code_ver
    return code_ver

def prepare_destination(pgconn, stconn, bucket_code_ver):
    assert None not in bucket_code_ver
    sink_list = []

    report = ReportFeeder(pgconn, stconn)
    msm = MeasurementFeeder(pgconn)
    msm_exc = MeasurementExceptionFeeder(pgconn)
    badmeta = BadmetaFeeder(pgconn)
    for feeder in (report, msm, msm_exc, badmeta):
        sink_list.append(feeder.init_sink(pgconn))

    # `body` is dummy feeder to mimic feeder/sink protocol and be able to flush
    # rows into DB while processing measurements one-by-one.
    body = BodySimhashDummyFeeder()
    body.sink = BodySimhashSink(stconn)
    sink_list.append(body.sink)

    # badrow_sink does not need dummy feeder as `__flush_stubborn()` calls
    # write() explicitly and double fault just raises exception and aborts.
    badrow_sink = PGCopyFrom(pgconn, BadrowFeeder.sink_table, columns=BadrowFeeder.columns)

    # Okay, "special" tables are done, let's register more generic DATA_TABLES.
    data_tables_args = {
        DnsFeeder: (pgconn,),
        HttpRequestFPFeeder: (pgconn,),
        HttpRequestFeeder: (body.sink,),
        HttpControlFeeder: (body.sink,),
    }
    data_tables = {} # class -> feeder instance
    ver_feeders = {} # code_ver -> list of feeders
    for ver in bucket_code_ver:
        flist = []
        for cls in DATA_TABLES:
            if ver < cls.min_compat_code_ver: # what a useful table for this version!
                if cls not in data_tables:
                    feeder = cls(*data_tables_args.get(cls, tuple())) # feels a bit like perl :-/
                    sink_list.append(feeder.init_sink(pgconn, badrow_sink))
                    data_tables[cls] = feeder
                flist.append(data_tables[cls])
        if HttpRequestFeeder in flist or HttpControlFeeder in flist:
            flist.append(body)
        ver_feeders[ver] = flist

    # `badrow_sink` has to be created before `data_tables` feeders, but
    # it can be closed only AFTER all sink for those feeders are closed.
    sink_list.append(badrow_sink)

    feeder_list = list(data_tables.values())
    feeder_list.extend((body, badmeta, msm_exc, msm, report))

    return report, msm, msm_exc, badmeta, ver_feeders, sink_list, feeder_list

def copy_data_from_autoclaved(pgconn, stconn, in_root, bucket, bucket_code_ver):
    TrappedException = None if FLAG_FAIL_FAST else Exception

    report, msm, msm_exc, badmeta, ver_feeders, sink_list, feeder_list = prepare_destination(
            pgconn, stconn, bucket_code_ver)
    assert None not in ver_feeders
    # `NULL` is special `code_ver`, but `NULL` and `0` are same for DATA_TABLES
    if CODE_VER_REPROCESS in bucket_code_ver:
        ver_feeders[None] = ver_feeders[CODE_VER_REPROCESS]

    for code_ver, autoclaved_no, report_no, msm_no, datum in iter_autoclaved_datum(pgconn, in_root, bucket):
        queue, exc = [], []
        if code_ver is None:
            try:
                row = report.report_row(report_no, datum)
            except TrappedException:
                badmeta.sink.write(badmeta.badmeta_row(
                    autoclaved_no, report_no, report=sys.exc_info()))
                continue # skip measurement with bad metadata
            else:
                queue.append((report.sink, row))
        for feeder in ver_feeders[code_ver]:
            try:
                if FLAG_DEBUG_CHAOS and random.random() < 0.01:
                    raise RuntimeError('bad luck with ordinary feeder')
                row = feeder.row(msm_no, datum)
            except TrappedException:
                exc.append(exc_hash(sys.exc_info()))
            else:
                queue.append((feeder.sink, row))
        if code_ver is None:
            # NB: report feeder is last pop() handler; there are no pop_handlers for `UPDATE`!
            for feeder in ver_feeders[code_ver] + [report]:
                try:
                    # `residual` is not updated during `reprocess` step
                    feeder.pop(datum)
                    # chaos is injected after pop() to avoid `residual` table pollution
                    if FLAG_DEBUG_CHAOS and random.random() < 0.01:
                        raise RuntimeError('bad luck with feeder.pop')
                except TrappedException:
                    exc.append(exc_hash(sys.exc_info()))
        try:
            feeder = msm if code_ver is None else msm_exc
            row = feeder.msm_rownpop(msm_no, datum, exc)
        except TrappedException:
            badmeta.sink.write(badmeta.badmeta_row(
                autoclaved_no, report_no, measurement=sys.exc_info()))
            continue # skip measurement with bad metadata
        else:
            queue.append((feeder.sink, row))
        for sink, row in queue:
            sink.write(row)
    # It is important to close sinks and feeders in that order because of
    # possible cross-table joins in `feeder.close()`.
    for sink in sink_list:
        sink.close()
    for feeder in feeder_list:
        feeder.close()

def iter_autoclaved_datum(pgconn, autoclaved_root, bucket):
    # The query to fetch LZ4 metadata for files takes ~466 bytes per row if all
    # the data is fetched in the memory of this process, 2014-11-22 has ~1e6
    # measurements so server-side cursor is used as a safety net against OOM.
    with pgconn.cursor('lz4meta') as cmeta:
        cmeta.itersize = 2*1024**2 / 466
        cmeta.execute('''
            SELECT filename, file_size, file_crc32, file_sha1,
                   frame_off, frame_size,
                   intra_off, intra_size, NULL AS code_ver, autoclaved_no, report_no, msm_no
            FROM autoclaved_meta
            JOIN report_meta USING (autoclaved_no)
            JOIN measurement_meta USING (report_no)

            UNION ALL

            SELECT filename, file_size, file_crc32, file_sha1,
                   frame_off, frame_size,
                   intra_off, intra_size, code_ver, autoclaved_no, report_no, msm_no
            FROM autoclaved
            JOIN report USING (autoclaved_no)
            JOIN measurement USING (report_no)
            WHERE bucket_date = %s AND code_ver < %s

            ORDER BY filename, frame_off, intra_off
        ''', [bucket, CODE_VER])
        for (filename, file_size, file_crc32, file_sha1), itfile in groupby(cmeta, itemgetter(0, 1, 2, 3)):
            print 'Processing autoclaved {}'.format(filename)
            with open(os.path.join(autoclaved_root, filename)) as fd:
                fd = ChecksummingTee(fd, NopTeeFd)
                for (frame_off, frame_size), itframe in groupby(itfile, itemgetter(4, 5)):
                    fd.seek(frame_off)
                    blob = fd.read(frame_size)
                    if len(blob) != frame_size:
                        raise RuntimeError('Unexpected end of file', filename, frame_off, frame_size, len(blob))
                    blob = lz4frame.decompress(blob)
                    for (_,_,_,_,_,_, intra_off, intra_size, code_ver, autoclaved_no, report_no, msm_no) in itframe:
                        datum = blob[intra_off:intra_off+intra_size]
                        if len(datum) != intra_size:
                            raise RuntimeError('Short LZ4 frame', filename, frame_off, intra_off)
                        datum = ujson.loads(datum)
                        yield code_ver, autoclaved_no, report_no, msm_no, datum
                for _ in iter(functools.partial(fd.read, 4096), ''):
                    pass # skip till EOF
                db_cksum = (file_size, file_crc32, str(file_sha1)) # file_sha1 is returned as buffer()
                fd_cksum = (fd.size, fd.crc32, fd.sha1)
                if db_cksum != fd_cksum:
                    raise RuntimeError('Checksum mismatch', filename, db_cksum, fd_cksum)

def none_if_len0(obj):
    return obj if len(obj) else None

def pop_values(obj):
    if isinstance(obj, basestring):
        return ''
    elif obj is None:
        return None
    elif isinstance(obj, bool): # assert isinstance(True, numbers.Number)
        return True
    elif isinstance(obj, numbers.Number):
        return 0
    elif isinstance(obj, list):
        for ndx in xrange(len(obj)):
            obj[ndx] = pop_values(obj[ndx])
        while len(obj) and isinstance(obj[-1], (list, dict)) and len(obj[-1]) == 0:
            obj.pop()
    elif isinstance(obj, dict):
        for key in obj.keys():
            obj[key] = pop_values(obj[key])
            if isinstance(obj[key], (list, dict)) and len(obj[key]) == 0:
                del obj[key]
    return obj

class BaseFeeder(object):
    sink_table = None
    columns = None
    def init_sink(self, pgconn, badsink=None):
        # It's rather convenient to initialize sink as a separate action as there are sinks
        # that have no explicit feeders, so all sinks should be a bit "separate".
        self.sink = PGCopyFrom(pgconn, self.sink_table, columns=self.columns, badsink=badsink)
        return self.sink
    def close(self):
        pass # assert self.sink.closed

class MeasurementFeeder(BaseFeeder):
    sink_table = 'measurement_blob'
    columns = ('msm_no', 'measurement_start_time', 'test_runtime', 'id', 'input', 'exc', 'residual')
    def __init__(self, pgconn):
        self.pgconn = pgconn
        create_temp_table(pgconn, self.sink_table, '''
            msm_no                  integer NOT NULL,
            measurement_start_time  timestamp without time zone,
            test_runtime            real,
            id                      uuid NOT NULL,
            input                   text,
            exc                     integer[],
            residual                jsonb NOT NULL
        ''')
    @staticmethod
    def msm_rownpop(msm_no, datum, exc):
        if FLAG_DEBUG_CHAOS and random.random() < 0.01:
            raise RuntimeError('bad luck with measurement')
        input_txt = datum.pop('input') # may be `list`
        if input_txt is not None and not isinstance(input_txt, basestring):
            input_txt = '{}:{}'.format(*input_txt)
        measurement_start_time = datum.pop('measurement_start_time')
        test_runtime = datum.pop('test_runtime')
        id_ = datum.pop('id')
        datum = pop_values(datum)
        return '{:d}\t{}\t{}\t{}\t{}\t{}\t{}\n'.format(
                    msm_no,
                    pg_quote(measurement_start_time), # nullable
                    pg_quote(test_runtime), # nullable
                    pg_quote(id_),
                    pg_quote(input_txt), # nullable
                    pg_quote(none_if_len0(exc)),
                    pg_quote(ujson.dumps(datum)))
    def close(self):
        with self.pgconn.cursor() as c:
            c.execute('''
                INSERT INTO input (input)
                SELECT DISTINCT input FROM measurement_blob WHERE input IS NOT NULL
                ON CONFLICT DO NOTHING
            ''')
            c.execute('''
                INSERT INTO residual (residual)
                SELECT DISTINCT residual FROM measurement_blob
                ON CONFLICT DO NOTHING
            ''')
            c.execute('''
                INSERT INTO measurement
                SELECT msm_no, report_no, frame_off, frame_size, intra_off, intra_size,
                measurement_start_time, test_runtime, orig_sha1, id, input_no, exc, residual_no
                FROM measurement_meta
                JOIN measurement_blob USING (msm_no)
                LEFT JOIN input USING (input)
                LEFT JOIN residual USING (residual)
            ''') # TODO: `LEFT JOIN measurement_blob_` to fail fast
        del self.pgconn

class MeasurementExceptionFeeder(BaseFeeder):
    sink_table = 'measurement_exc'
    columns = ('msm_no', 'exc')
    def __init__(self, pgconn):
        self.pgconn = pgconn
        create_temp_table(pgconn, self.sink_table, 'msm_no integer NOT NULL, exc integer[] NOT NULL')
    @staticmethod
    def msm_rownpop(msm_no, _, exc):
        if FLAG_DEBUG_CHAOS and random.random() < 0.01:
            raise RuntimeError('bad luck with measurement')
        return '{:d}\t{}\n'.format(msm_no, pg_quote(exc)) if len(exc) else ''
    def close(self):
        with self.pgconn.cursor() as c:
            c.execute('''
                UPDATE measurement msm
                SET exc = array_append(msm.exc, NULL) || mex.exc
                FROM measurement_exc mex
                WHERE mex.msm_no = msm.msm_no
            ''')
        del self.pgconn


# Python WTF:
# >>> '{}\t{}\t{}\t{}\t{}\t{}\n'.format(1,2,3,4,5,6,7)
# '1\t2\t3\t4\t5\t6\n'
# >>> '%s\t%s\t%s\t%s\t%s\t%s\n' % (1,2,3,4,5,6,7)
# Traceback (most recent call last):
#   File "<stdin>", line 1, in <module>
# TypeError: not all arguments converted during string formatting

class ReportFeeder(BaseFeeder):
    sink_table = 'report_blob'
    columns = ('report_no', 'test_start_time', 'probe_cc', 'probe_asn', 'probe_ip', 'test_name',
               'report_id', 'software_no')
    sw_key = ('test_name', 'test_version', 'software_name', 'software_version')
    # common_keys must be same for every measurement in the report file
    common_keys = ('test_start_time', 'probe_cc', 'probe_asn', 'probe_ip', 'report_filename',
       'test_name', 'test_version', 'software_name', 'software_version', 'report_id')
    def __init__(self, pgconn, stconn):
        self.pgconn = pgconn
        create_temp_table(pgconn, self.sink_table, '''
            report_no       integer NOT NULL,
            test_start_time timestamp without time zone NOT NULL,
            probe_cc        character(2) NOT NULL,
            probe_asn       integer NOT NULL,
            probe_ip        inet,
            test_name       ootest,
            report_id       text,
            software_no     integer NOT NULL
        ''')
        with pgconn.cursor() as c:
            c.execute('SELECT unnest(enum_range(NULL::ootest))')
            self.ootest_enum = {_[0] for _ in c.fetchall()}
        self.software_no = PostgresDict(stconn, 'software', 'software_no', self.sw_key)
        self.prev_no = None
        self.prev_keys = None # value is not actually used
    def report_row(self, report_no, datum):
        if self.prev_no == report_no:
            for ndx, key in enumerate(self.common_keys):
                if self.prev_keys[ndx] != datum[key]: # also enforces existence of common_keys
                    raise RuntimeError('report key mismatch', key, self.prev_keys, datum[key])
            return ''
        else:
            self.prev_keys = tuple(datum[key] for key in self.common_keys)
            self.prev_no = report_no
        if FLAG_DEBUG_CHAOS and random.random() < 0.01:
            raise RuntimeError('bad luck with report row')
        software_no = self.software_no[tuple(datum[key] for key in self.sw_key)]
        if datum['probe_asn'][:2] != 'AS':
            raise RuntimeError('Bad AS number', datum['probe_asn'])
        probe_asn = int(datum['probe_asn'][2:])
        if len(datum['probe_cc']) != 2:
            raise RuntimeError('Bad probe_cc len', datum['probe_cc'])
        probe_ip = datum['probe_ip']
        if probe_ip == '127.0.0.1':
            probe_ip = None
        test_name = datum['test_name']
        if test_name not in self.ootest_enum:
            test_name = None # it's still saved in `software_no`
        report_id = datum['report_id']
        if not report_id: # null, empty string - anything
            report_id = None
        return '{:d}\t{}\t{}\t{:d}\t{}\t{}\t{}\t{:d}\n'.format(
                report_no,
                datum['test_start_time'],
                datum['probe_cc'],
                probe_asn,
                pg_quote(probe_ip),
                pg_quote(test_name),
                pg_quote(report_id),
                software_no)
    @classmethod
    def pop(cls, datum):
        # TODO: strictly speaking, `report_filename` is not validated against
        # data fetched with copy_reports_from_index()
        for key in cls.common_keys:
            datum.pop(key, None)
    def close(self): # also handles TABLE `report_meta`
        with self.pgconn.cursor() as c:
            c.execute('''
                INSERT INTO report
                SELECT report_no, autoclaved_no, test_start_time, probe_cc, probe_asn, probe_ip,
                       test_name, badtail, textname, orig_sha1,
                       COALESCE(report_id, translate(encode(orig_sha1, 'base64'), '/+=', '_-')), software_no
                FROM report_meta
                JOIN report_blob USING (report_no)
            ''') # TODO: `LEFT JOIN report_blob` to fail fast in case of errors
        del self.pgconn


TRACEBACK_LINENO_RE = re.compile(r' line \d+,')

def exc_hash(exc_info):
    # exc_hash ignores line numbers, but does not ignore other taceback values
    type_, value_, traceback_ = exc_info
    msg = ''.join(traceback.format_exception(type_, None, traceback_))
    msg = TRACEBACK_LINENO_RE.sub(' line N,', msg)
    ret = mmh3.hash(msg) & 0xffff0000
    msg = traceback.format_exception_only(type_, value_)
    assert len(msg) == 1
    msg = msg[0]
    ret |= mmh3.hash(msg) & 0xffff
    return to_signed32(ret)

class BadmetaFeeder(BaseFeeder):
    # no `min_compat_code_ver`, it's not a usual data table
    sink_table = 'badmeta_'
    columns = ('autoclaved_no', 'report_no', 'exc_report', 'exc_measurement')
    def __init__(self, pgconn):
        self.pgconn = pgconn
        create_temp_table(pgconn, self.sink_table, '''
            autoclaved_no   integer NOT NULL,
            report_no       integer NOT NULL,
            exc_report      integer,
            exc_measurement integer,
            CHECK (exc_report IS NOT NULL OR exc_measurement IS NOT NULL)
        ''')
    @staticmethod
    def badmeta_row(autoclaved_no, report_no, report=None, measurement=None):
        return '{:d}\t{:d}\t{}\t{}\n'.format(
                autoclaved_no,
                report_no,
                pg_quote(exc_hash(report) if report is not None else None),
                pg_quote(exc_hash(measurement) if measurement is not None else None))
    def close(self):
        with self.pgconn.cursor() as c:
            c.execute('''
            INSERT INTO badmeta
            SELECT
                badmeta_.autoclaved_no,
                badmeta_.report_no,
                COALESCE(array_agg(exc_report) FILTER (WHERE exc_report IS NOT NULL), ARRAY[]::int4[]),
                COALESCE(array_agg(exc_measurement) FILTER (WHERE exc_measurement IS NOT NULL), ARRAY[]::int4[])
            FROM badmeta_
            GROUP BY badmeta_.autoclaved_no, badmeta_.report_no
            ''')
        del self.pgconn


class BadrowFeeder(object):
    # no `min_compat_code_ver`, it's not a usual data table
    sink_table = 'badrow'
    columns = ('tbl', 'code_ver', 'datum')
    @staticmethod
    def badrow_row(table, datum):
        return '{}\t{:d}\t\\\\x{}\n'.format(pg_quote(table), CODE_VER, datum.encode('hex'))

IPV4_RE = re.compile(r'^\d+\.\d+\.\d+\.\d+$')

class TcpFeeder(BaseFeeder):
    min_compat_code_ver = 2
    data_table = sink_table = 'tcp'
    columns = ('msm_no', 'ip', 'port', 'control_failure', 'test_failure', 'control_api_failure')
    # NB: control_api_failure is also recorded as `control_failure` in `http_verdict`
    @staticmethod
    def row(msm_no, datum):
        ret = ''
        test_keys = datum['test_keys']
        control = test_keys.get('control', {}).get('tcp_connect', {})
        control_api_failure = test_keys.get('control_failure')
        for el in test_keys.get('tcp_connect', ()):
            ip, port, failure = el['ip'], el['port'], el['status']['failure']
            assert failure is not None or (el['status']['success'] == True and el['status']['blocked'] == False)
            if IPV4_RE.match(ip): # domains?! why?! # TODO: is not IPv6-ready :-(
                elctrl = control.get('{}:{:d}'.format(ip, port))
                if elctrl:
                    assert control_api_failure is None
                    assert isinstance(elctrl['status'], bool) and elctrl['status'] == (elctrl['failure'] is None)
                    control_failure = elctrl['failure']
                else:
                    # FALSE: assert control_api_failure is not None
                    # Shit happens: {... "control": {}, "control_failure": null, ...}
                    # TODO: ^^ be smarter in this case
                    control_failure = None # well, it's hard to state anything about `control_api_failure`
                ret += '{:d}\t{}\t{:d}\t{}\t{}\t{}\n'.format(
                        msm_no,
                        ip,
                        port,
                        pg_quote(control_failure),
                        pg_quote(failure),
                        pg_quote(control_api_failure))
        return ret
    @staticmethod
    def pop(datum):
        test_keys = datum['test_keys']
        control = test_keys.get('control', {}).get('tcp_connect', {})
        test_keys.pop('control_failure', None)

        for el in test_keys.get('tcp_connect', ()):
            ip, port, _ = el.pop('ip'), el.pop('port'), el['status'].pop('failure')
            el['status'].pop('success'), el['status'].pop('blocked')
            elctrl = control.get('{}:{:d}'.format(ip, port))
            if elctrl:
                elctrl.pop('status')
                elctrl.pop('failure')

class DnsFeeder(BaseFeeder):
    min_compat_code_ver = 2
    data_table, sink_table = 'dns_a', 'dns_a_'
    columns = ('msm_no', 'domain', 'control_ip', 'test_ip', 'control_cname', 'test_cname',
               'ttl', 'resolver_hostname', 'client_resolver', 'control_failure', 'test_failure')
    # TTL of the first DNS RR of the answer is taken, it SHOULD be RR
    # describing `hostname`, but there is no guarantee for that. :-(
    # Different RRs may have different TTL in the answer, e.g.:
    # cname-to-existing-dual.ya.darkk.net.ru. 14400 IN CNAME linode.com.
    # linode.com.                               210 IN A     72.14.191.202
    # linode.com.                               210 IN A     69.164.200.202
    # linode.com.                               210 IN A     72.14.180.202
    def __init__(self, pgconn):
        self.pgconn = pgconn
        create_temp_table(pgconn, self.sink_table, '''
            msm_no              integer NOT NULL,
            domain              text NOT NULL,
            control_ip          inet[],
            test_ip             inet[],
            control_cname       text[],
            test_cname          text[],
            ttl                 integer,
            resolver_hostname   inet,
            client_resolver     inet,
            control_failure     text,
            test_failure        text
        ''')
    @staticmethod
    def row(msm_no, datum):
        test_keys = datum['test_keys']
        client_resolver = test_keys.get('client_resolver')
        dns = test_keys.get('control', {}).get('dns', {})
        control_failure = dns.get('failure')
        addrs = dns.get('addrs', ())
        control_ip = none_if_len0(sorted(filter(IPV4_RE.match, addrs)))
        control_cname = none_if_len0([_ for _ in addrs if _ not in control_ip]) # O(n^2), but list is tiny
        queries = test_keys.get('queries', ())
        if len({q['hostname'] for q in queries}) != 1:
            control_ip, control_cname, control_failure = None, None, '[ambiguous]'
        ret = ''
        for q in queries:
            if q['query_type'] == 'A': # almost always
                ttl = dns_ttl(next(iter(q['answers']), {}).get('ttl'))
                test_ip = none_if_len0(sorted([a['ipv4'] for a in q['answers'] if a['answer_type'] == 'A']))
                test_cname = none_if_len0([a['hostname'] for a in q['answers'] if a['answer_type'] == 'CNAME'])
                ret += '{:d}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n'.format(
                        msm_no,
                        pg_quote(q['hostname']),
                        pg_quote(control_ip),
                        pg_quote(test_ip),
                        pg_quote(control_cname),
                        pg_quote(test_cname),
                        pg_quote(ttl),
                        pg_quote(q['resolver_hostname']),
                        pg_quote(client_resolver),
                        pg_quote(control_failure),
                        pg_quote(q['failure']))
        return ret
    @staticmethod
    def pop(datum):
        test_keys = datum['test_keys']
        test_keys.pop('client_resolver', None)
        dns = test_keys.get('control', {}).get('dns', {})
        dns.pop('failure', None)
        dns.pop('addrs', None)
        queries = test_keys.get('queries', ())
        for q in queries:
            if q['query_type'] == 'A': # almost always
                if len(q['answers']):
                    first_ttl = q['answers'][0].get('ttl', object())
                    for a in q['answers']:
                        if a.get('ttl') == first_ttl:
                            a.pop('ttl')
                        if a['answer_type'] == 'A':
                            a.pop('ipv4')
                            a.pop('answer_type')
                        elif a['answer_type'] == 'CNAME':
                            a.pop('hostname')
                            a.pop('answer_type')
                q.pop('hostname')
                q.pop('resolver_hostname')
                q.pop('failure')
    def close(self):
        with self.pgconn.cursor() as c:
            c.execute('''
                INSERT INTO domain (domain)
                SELECT DISTINCT domain FROM dns_a_
                UNION
                SELECT DISTINCT UNNEST(control_cname) FROM dns_a_
                UNION
                SELECT DISTINCT UNNEST(test_cname) FROM dns_a_
                ON CONFLICT DO NOTHING
            ''')
            c.execute('''
                INSERT INTO dns_a
                SELECT
                    msm_no,
                    (SELECT domain_no FROM domain WHERE domain.domain = dns_a_.domain) AS domain_no,
                    control_ip, test_ip,
                    (SELECT array_agg(domain_no ORDER BY ndx)
                     FROM unnest(control_cname) WITH ORDINALITY t2(domain, ndx)
                     LEFT JOIN domain USING (domain)) AS control_cname,
                    (SELECT array_agg(domain_no ORDER BY ndx)
                     FROM unnest(test_cname) WITH ORDINALITY t2(domain, ndx)
                     LEFT JOIN domain USING (domain)) AS test_cname,
                    ttl, resolver_hostname, client_resolver, control_failure, test_failure
                FROM dns_a_
            ''')
        del self.pgconn


class BodySimhashDummyFeeder(object):
    fake_row = object()
    @staticmethod
    def row(msm_no, datum):
        return BodySimhashDummyFeeder.fake_row
    @staticmethod
    def close():
        pass

class BodySimhashSink(object):
    # NB: this data goes to small-transaction connection (stconn) to be
    # available to other nodes as soon as it's commited.
    # Queue is buffered to avoid round-trip to database for every webpage.
    # Computation is delayed till filling the database as it's rather
    # expensive, throughput is ~7.5 Mbytes/s, so roundtrip to DB is done to
    # exclude already parsed pages. It's unclear if extra roundtrip makes sense
    # when known_sha256 cache is used.
    # Average body size is 75kb and cross-report cachehit is ~18%.
    fake_row = object()
    def __init__(self, stconn):
        self.stconn = stconn
        self.known_sha256 = IsKnownL2(85000, 15000)
        self.queue = {}
        self.known = 0
        self.size = 0
    def put(self, body_sha256, body):
        if FLAG_SKIP_SIMHASH:
            return
        assert isinstance(body_sha256, str) and isinstance(body, str)
        if self.known_sha256.is_known(body_sha256): # either in DB or in queue
            self.known += 1
            return
        self.queue[body_sha256] = body
        self.size += len(body)
        # `write()` is not called from `put()` to have clean place to raise
        # exception from, as there are several places calling `put()` guardede
        # by TrappedException and exception in `flush()` should be fatal.
    def write(self, row):
        assert row is BodySimhashDummyFeeder.fake_row
        if self.size > 16777216 or len(self.queue) > 2048:
            self.flush()
    def flush(self):
        with self.stconn, self.stconn.cursor() as c:
            # NB: https://www.datadoghq.com/blog/100x-faster-postgres-performance-by-changing-1-line/ when postgres < 9.3
            c.execute('SELECT body_sha256 FROM http_body_simhash WHERE body_sha256 = ANY(%s)',
                [map(psycopg2.Binary, self.queue.iterkeys())])
            just_fetched = [str(_[0]) for _ in c]
            for body_sha256 in just_fetched:
                del self.queue[body_sha256]
            args = []
            for body_sha256, body in self.queue.iteritems():
                hi, lo = sim_shi4_mm3(body)
                hi, lo = to_signed(hi), to_signed(lo)
                args.append(psycopg2.Binary(body_sha256)) # http://initd.org/psycopg/docs/usage.html#binary-adaptation
                args.append(hi)
                args.append(lo)
            assert len(args) % 3 == 0
            if len(args):
                c.execute('INSERT INTO http_body_simhash (body_sha256, simhash_shi4mm3hi, simhash_shi4mm3lo) VALUES {} '
                          'ON CONFLICT DO NOTHING RETURNING body_sha256'.format(
                          ', '.join(['(%s, %s, %s)'] * (len(args) / 3))),
                          args)
                just_inserted = {_[0] for _ in c}
            else:
                just_inserted = {}
            print 'BodySimhashSink: skipped {:d} queue {:d} pre-filter {:d} db-dup {:d}'.format(
                    self.known,
                    len(self.queue) + len(just_fetched),
                    len(just_fetched),
                    len(self.queue) - len(just_inserted))
        self.queue.clear()
        self.known = 0
        self.size = 0
    def close(self):
        self.flush()
        del self.stconn, self.queue, self.known_sha256

class VanillaTorFeeder(BaseFeeder):
    min_compat_code_ver = 4
    data_table = sink_table = 'vanilla_tor'
    columns = ('msm_no', 'timeout', 'error', 'tor_progress',  'success', 'tor_progress_tag', 'tor_progress_summary', 'tor_version', 'tor_log')

    @staticmethod
    def row(msm_no, datum):
        if datum['test_name'] != 'vanilla_tor':
            return ''
        t = datum['test_keys']

        success = t.get('success', None)
        if success is None:
            if t['tor_log'] is None and t['tor_progress_tag'] is None and t['tor_progress'] == 0 and t['timeout'] > 60 and t['error'] is None and t['tor_progress_summary'] is None:
                # That's usual garbage (~0.5% of measurements) like following json, it does not deserve a row in the database
                # You can check that it's nothing but garbage with following one-liner:
                # $ for f in ????-??-??/vanilla_tor*.tar.lz4; do tar -I lz4 -x --to-stdout -f $f; done | jq -c 'select(.test_keys.success == null) | .test_keys' | sort | uniq -c
                # {"transport_name":"vanilla","success":null,"tor_log":null,"tor_progress_tag":null,"tor_progress":0,"timeout":300,"error":null,"tor_version":"0.2.5.12","tor_progress_summary":null}
                return ''
            raise RuntimeError('Non-trivial data while .test_keys.success is null')

        if t.get('transport_name') not in (None, 'vanilla'):
            raise RuntimeError('`vanilla_tor` data with non-vanilla `transport_name`', t.get('transport_name'))

        # XXX: is' unclear if it's useful as `text` value
        #  40255 null
        #   2037 "timeout-reached"
        error = t.get('error', None)

        # XXX: it's unclear if it's useful column in database
        #      1 100000000
        #      1 120
        #      2 200
        #  42288 300
        timeout = t.get('timeout', 0)

        tor_progress = t.get('tor_progress')
        if tor_progress is None:
            tor_progress = 0
        tor_log = t.get('tor_log')
        if tor_log:
            tor_log = ujson.dumps(parse_tor_log(tor_log))

        return '{:d}\t{:d}\t{}\t{:d}\t{}\t{}\t{}\t{}\t{}\n'.format(
                    msm_no,
                    timeout,
                    pg_quote(error),
                    tor_progress,
                    pg_quote(success),
                    pg_quote(t.get('tor_progress_tag')), # XXX: looks like dup of `tor_progress`
                    pg_quote(t.get('tor_progress_summary')), # XXX: looks like dup of `tor_progress`
                    pg_quote(t.get('tor_version', '0.0.0')), # fav versions are "00:40:28.580", "22:09:16.876" and "None"
                    pg_quote(tor_log))

    @staticmethod
    def pop(datum):
        t = datum['test_keys']
        known_keys = ('success', 'transport_name', 'error', 'timeout',
                'tor_progress', 'tor_log', 'tor_progress_tag',
                'tor_progress_summary', 'tor_version')
        for key in known_keys:
            t.pop(key)

TITLE_REGEXP = re.compile('<title>(.*?)</title>', re.IGNORECASE | re.DOTALL)

def get_title(body):
    if body is None:
        return None
    title = TITLE_REGEXP.search(body)
    if title:
        title = title.group(1).decode('utf-8', 'replace').encode('utf-8')
    return title

class BaseHttpFeeder(BaseFeeder):
    def __init__(self, body_sink):
        self.body_sink = body_sink
    def body_sha256(self, body):
        if body is not None:
            body_sha256 = hashlib.sha256(body)
            digest = body_sha256.digest()
            self.body_sink.put(digest, body)
            body_sha256 = pg_binquote(digest)
        else:
            body_sha256 = pg_quote(None)
        return body_sha256
    COMMON_HEADERS = {
        'Accept-Language': 'en-US;q=0.8,en;q=0.5',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36'
    }
    @classmethod
    def _pop_request(cls, datum, request): # .test_keys.requests[].request element
        if 'url' in request and request['url'] == datum['input']: # may be already popped
            del request['url']
        if request['body'] in ('', None): # both happens
            del request['body']
        if request['headers'] == cls.COMMON_HEADERS:
            del request['headers']
        if request['method'] == 'GET':
            del request['method']
        tor = request.get('tor')
        if tor is not None: # it should not be `null`, it's dict
            tor.pop('is_tor')
            if tor['exit_ip'] is None:
                tor.pop('exit_ip')
            if tor['exit_name'] is None:
                tor.pop('exit_name')

class HttpControlFeeder(BaseHttpFeeder):
    min_compat_code_ver = 2
    data_table = sink_table = 'http_control'
    columns = ('msm_no', 'is_tor', 'failure', 'status_code', 'body_length', 'title', 'headers', 'body_sha256')
    def row(self, msm_no, datum):
        ret = ''
        if datum['test_name'] == 'web_connectivity':
            r = datum['test_keys']['control'].get('http_request')
            if r:
                # {"id":"8e21031a-6c52-4659-ba30-016d533c2451","report_id":"20170421T070023Z_AS131709_rKyNp02D3ZZAMYwaeElF7bWjUGusiVcTc4EEoPqAhw4uwlD0Dj"}
                status_code = r.get('status_code')
                if status_code == -1:
                    status_code = None
                body_length = r.get('body_length')
                if body_length == -1:
                    body_length = None
                ret = '{:d}\tFALSE\t{}\t{}\t{}\t{}\t{}\t\\N\n'.format(
                        msm_no,
                        pg_quote(r['failure']),
                        pg_quote(http_status_code(status_code)),
                        pg_quote(body_length),
                        pg_quote(r.get('title')),
                        pg_quote(ujson.dumps(http_headers(r['headers'])))) # seems, empty headers dict is still present it case of failure
        elif datum['test_name'] == 'http_requests':
            for r in datum['test_keys']['requests']:
                if r['request']['tor']['is_tor']:
                    response = r['response']
                    body = httpt_body(response)
                    body_sha256 = self.body_sha256(body)
                    if response is None:
                        response = {}
                    headers = response.get('headers')
                    if headers is not None:
                        headers = ujson.dumps(http_headers(headers))
                    ret += '{:d}\tTRUE\t{}\t{}\t{}\t{}\t{}\t{}\n'.format(
                        msm_no,
                        pg_quote(r.get('failure')),
                        pg_quote(http_status_code(response.get('code'))),
                        pg_quote(len(body) if body is not None else r.get('response_length')),
                        pg_quote(get_title(body)),
                        pg_quote(headers),
                        body_sha256)
        return ret
    def pop(self, datum):
        if datum['test_name'] == 'web_connectivity':
            r = datum['test_keys']['control'].get('http_request')
            if r:
                r.pop('status_code', None)
                r.pop('body_length', None)
                r.pop('failure')
                r.pop('title', None)
                r.pop('headers')
        elif datum['test_name'] == 'http_requests':
            for r in datum['test_keys']['requests']:
                if r['request']['tor'].get('is_tor') == True: # may be popped by HttpRequestFeeder
                    response = r['response']
                    if response is not None:
                        response.pop('body')
                        r.pop('failure', None)
                        response.pop('code', None)
                        r.pop('response_length', None)
                        response.pop('headers')
                    else:
                        r.pop('response')
                    self._pop_request(datum, r['request'])


class HttpRequestFeeder(BaseHttpFeeder):
    min_compat_code_ver = 2
    data_table = sink_table = 'http_request'
    columns = ('msm_no', 'url', 'failure', 'status_code', 'body_length', 'title', 'headers', 'body_sha256')
    def row(self, msm_no, datum):
        ret = ''
        if datum['test_name'] == 'web_connectivity':
            for r in datum['test_keys']['requests']:
                # ooniprobe-android does NOT set `tor` dict, it's also not set in case of DNS failure
                assert 'tor' not in r['request'] or not r['request']['tor']['is_tor']
                ret += self._row(msm_no, r)
        elif datum['test_name'] == 'http_requests':
            for r in datum['test_keys']['requests']:
                if not r['request']['tor']['is_tor']:
                    ret += self._row(msm_no, r)
        return ret
    def _row(self, msm_no, r):
        response = r['response']
        body = httpt_body(response)
        body_sha256 = self.body_sha256(body)
        if response is None: # may be `null` both for web_connectivity and http_requests
            response = {}
        headers = response.get('headers')
        if headers is not None:
            headers = ujson.dumps(http_headers(headers))
        return '{:d}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n'.format(
            msm_no,
            pg_quote(r['request']['url']),
            pg_quote(r.get('failure')),
            pg_quote(http_status_code(response.get('code'))),
            pg_quote(len(body) if body is not None else r.get('response_length')),
            pg_quote(get_title(body)),
            pg_quote(headers),
            body_sha256)
    def pop(self, datum):
        if datum['test_name'] == 'web_connectivity':
            for r in datum['test_keys']['requests']:
                self._pop(datum, r)
        elif datum['test_name'] == 'http_requests':
            for r in datum['test_keys']['requests']:
                if r['request']['tor'].get('is_tor') == False: # may be popped by HttpControlFeeder
                    self._pop(datum, r)
    def _pop(self, datum, r):
        response = r['response']
        r['request'].pop('url') 
        r.pop('failure', None)
        if response is not None:
            response.pop('body')
            response.pop('code', None)
            response.pop('headers')
        else:
            r.pop('response')
        r.pop('response_length', None)
        self._pop_request(datum, r['request'])

class HttpRequestFPFeeder(HttpRequestFeeder):
    min_compat_code_ver = 3
    data_table = sink_table = 'http_request_fp'
    columns = ('msm_no', 'fingerprint_no')
    # It should probably become part of `http_request` and `http_control`
    # tables, but I'm too lazy to alter 40 Gb of tables right now...
    def __init__(self, pgconn):
        # NB: no super(...).__init__() call!
        self.header_prefix = {} # header -> [(prefix, no)]
        self.header_value = {}  # header -> {value: no}
        self.body_substr = []   # [(value, no)]
        # These data structures are not fancy at all, one may want to say that
        # something like Aho-Corasick search should be used to check bodies,
        # but pyahocorasick==1.1.4 that claims to be quite efficient works worse
        # than naive substring search loop for <=50 body_substr fingerprints.
        with pgconn.cursor() as c:
            c.execute('''
                select md5(
                    md5(array_agg(fingerprint_no    order by fingerprint_no)::text) ||
                    md5(array_agg(origin_cc         order by fingerprint_no)::text) ||
                    md5(array_agg(body_substr       order by fingerprint_no)::text) ||
                    md5(array_agg(header            order by fingerprint_no)::text) ||
                    md5(array_agg(header_prefix     order by fingerprint_no)::text) ||
                    md5(array_agg(header_value      order by fingerprint_no)::text) ||
                    ''
                ) from fingerprint
            ''')
            assert '916446978a4a86741d0236d19ce7157e' == next(c)[0], 'fingerprint table does not match CODE_VER={}'.format(CODE_VER)
            c.execute('SELECT fingerprint_no, body_substr, header, header_prefix, header_value FROM fingerprint')
            for fingerprint_no, body_substr, header, header_prefix, header_value in c:
                if body_substr is not None:
                    self.body_substr.append((body_substr, fingerprint_no))
                elif header_prefix is not None:
                    self.header_prefix.setdefault(header.lower(), []).append((header_prefix, fingerprint_no))
                elif header_value is not None:
                    self.header_value.setdefault(header.lower(), {})[header_value] = fingerprint_no
    def _row(self, msm_no, r):
        ret = ''
        response = r['response']
        body = httpt_body(response)
        if body is not None:
            for body_substr, fingerprint_no in self.body_substr:
                if body_substr in body:
                    ret += '{:d}\t{:d}\n'.format(msm_no, fingerprint_no)
        headers = {h.lower(): value for h, value in ((response or {}).get('headers') or {}).iteritems()}
        for h, header_value in self.header_value.iteritems():
            fingerprint_no = header_value.get(headers.get(h))
            if fingerprint_no is not None:
                ret += '{:d}\t{:d}\n'.format(msm_no, fingerprint_no)
        for h in self.header_prefix:
            if h in headers:
                value = headers[h]
                for header_prefix, fingerprint_no in self.header_prefix[h]:
                    if value.startswith(header_prefix):
                        ret += '{:d}\t{:d}\n'.format(msm_no, fingerprint_no)
        return ret
    def pop(self, datum):
        pass # done by HttpRequestFeeder

class HttpVerdictFeeder(BaseFeeder):
    min_compat_code_ver = 2
    data_table = sink_table = 'http_verdict'
    columns = ('msm_no', 'accessible', 'control_failure', 'http_experiment_failure', 'title_match',
               'dns_consistency', 'dns_experiment_failure', 'body_proportion', 'blocking',
               'body_length_match', 'headers_match', 'status_code_match')
    blndx = (columns.index('blocking') - 1) # may be BOTH bolean and text, needs some type convertion
    fmt = '{:d}\t' + '\t'.join(['{}'] * (len(columns) - 1)) + '\n'
    @classmethod
    def row(cls, msm_no, datum):
        it = iter(cls.columns)
        next(it) # skip msm_no
        row = [datum['test_keys'].get(_) for _ in it]
        if isinstance(row[cls.blndx], bool):
            row[cls.blndx] = 'true' if row[cls.blndx] else 'false' # enfoce string type
        return cls.fmt.format(msm_no, *map(pg_quote, row))
    @classmethod
    def pop(cls, datum):
        it = iter(cls.columns)
        next(it)
        test_keys = datum['test_keys']
        for key in it:
            test_keys.pop(key, None)

class PostgresDict(collections.defaultdict):
    # NB: `table`, `value` and `key` are trusted!
    # `maxsize` is used to avoid unlimited memory consumption by in-process cache
    def __init__(self, conn, table, value, key, maxsize=4194304):
        assert isinstance(key, tuple)
        collections.defaultdict.__init__(self)
        self.__conn = conn
        # Ouch, really ugly
        with self.__conn, conn.cursor() as c:
            c.execute('SELECT {}, {} FROM {}'.format(value, ', '.join(key), table))
            if len(key) == 1:
                for _ in c:
                    self[_[1]] = _[0]
            else:
                for _ in c:
                    self[_[1:]] = _[0]
        self.__select = 'SELECT {} FROM {} WHERE '.format(value, table) + ' AND '.join(_+' = %s' for _ in key)
        self.__insert = 'INSERT INTO {} ({}) VALUES({}) ON CONFLICT DO NOTHING RETURNING {}'.format(table, ', '.join(key),
                            ', '.join(['%s']*len(key)), value)
        size = self.getsizeof()
        if size > maxsize:
            raise RuntimeError('PostgresDict is huge, tune maxsize of refactor', size, maxsize, table, key, value)
    def getsizeof(self):
        if isinstance(next(self.iterkeys(), ()), tuple):
            return sys.getsizeof(self) + sum(sys.getsizeof(_k) + sys.getsizeof(_v) + sum(sys.getsizeof(_) for _ in _k) for _k, _v in self.iteritems())
        else:
            return sys.getsizeof(self) + sum(sys.getsizeof(_k) + sys.getsizeof(_v) for _k, _v in self.iteritems())
    def __missing__(self, key):
        assert isinstance(key, (tuple, basestring))
        with self.__conn, self.__conn.cursor() as c:
            dbkey = (key,) if isinstance(key, basestring) else key
            c.execute(self.__insert, dbkey)
            row = c.fetchone()
            if row is None:
                c.execute(self.__select, dbkey)
                row = c.fetchone()
            self[key] = row[0]
            return self[key]

DATA_TABLES = (
    TcpFeeder,
    DnsFeeder,
    VanillaTorFeeder,
    HttpControlFeeder,
    HttpRequestFeeder,
    HttpRequestFPFeeder,
    HttpVerdictFeeder,
)

class IsKnownL2(object):
    # Fixed-size in-memory set to check if some object is "known".
    # Two-layer Random-Replacement cache improves efficiency
    # measurably compared to one-big Random-Replacement cache.
    def __init__(self, l1, l2):
        self.__l1 = set()
        self.__l2 = set()
        self.__l1len = l1
        self.__l2len = l2
    def is_known(self, key):
        l1, l2 = self.__l1, self.__l2
        if key in l2:
            return True
        if key in l1:
            l1.remove(key)
            l2.add(key)
            if len(l2) > self.__l2len:
                l2.pop() # FIXME: not quite random element
            return True
        l1.add(key)
        if len(l1) > self.__l1len:
            l1.pop() # not quite random element
        return False

def meta_pg(in_root, bucket, postgres):
    assert in_root[-1] != '/' and '/' not in bucket and os.path.isdir(os.path.join(in_root, bucket))

    # 1. Tables use bucket suffix to allow concurrent workers filling different tables.
    # 2. Tables do NOT include random string in the suffix (like timestamp) to
    # avoid filling the disk with bad retries.  3. Tables are `UNLOGGED` and not
    # `TEMPORARY` as these tables may be shared across different sessions: DNS
    # metadata and TCP metadata are processed with COPY to different tables.

    pgconn = psycopg2.connect(dsn=postgres) # ordinary postgres connection
    stconn = psycopg2.connect(dsn=postgres) # short-transaction connection

    with pgconn, pgconn.cursor() as c: # main transaction
        load_global_duplicate_reports(pgconn)
        autoclaved_index = os.path.join(in_root, bucket, autoclaving.INDEX_FNAME)
        files = load_autoclaved_index(autoclaved_index)
        ingest, reingest, reprocess = load_autoclaved_db_todo(pgconn, files, bucket)
        if not (ingest or reingest or reprocess):
            print 'public/autoclaved and postgres are in sync, bucket={}'.format(bucket)
            return
        print 'bucket={}: ingest {:d}, reingest {:d}, reprocess {:d}'.format(bucket, len(ingest), len(reingest), len(reprocess))
        copy_meta_from_index(pgconn, ingest, reingest, autoclaved_index, bucket)
        bucket_code_ver = delete_data_to_reprocess(pgconn, bucket)
        del autoclaved_index, files
        copy_data_from_autoclaved(pgconn, stconn, in_root, bucket, bucket_code_ver)
        del bucket_code_ver
        # Okay, server-side cursor feeding indexes is closed and the code is
        # still alive, it's time to morph temporary tables that were not
        # touched by feeder.close()!
        c.execute('''
            UPDATE autoclaved
            SET code_ver = %s
            WHERE code_ver != %s AND bucket_date = %s
        ''', [CODE_VER, CODE_VER, bucket])
        if c.rowcount != len(reprocess):
            raise RuntimeError('Bad rowcount of reprocess files', c.rowcount, len(reprocess))
        c.execute('''
            INSERT INTO autoclaved
            SELECT
                autoclaved_no, filename, %s AS bucket_date, %s AS code_ver,
                file_size, file_crc32, file_sha1
            FROM autoclaved_meta
        ''', [bucket, CODE_VER])
        if c.rowcount != len(ingest) + len(reingest):
            raise RuntimeError('Bad rowcount in autoclaved_meta', c.rowcount, len(ingest), len(reingest))
    return

########################################################################

def parse_args():
    p = argparse.ArgumentParser(description='ooni-pipeline: public/autoclaved -> *')
    p.add_argument('--start', metavar='ISOTIME', type=isomidnight, help='Airflow execution date', required=True)
    p.add_argument('--end', metavar='ISOTIME', type=isomidnight, help='Airflow execution date + schedule interval', required=True)
    p.add_argument('--autoclaved-root', metavar='DIR', type=dirname, help='Path to .../public/autoclaved', required=True)
    p.add_argument('--postgres', metavar='DSN', help='libpq data source name')

    opt = p.parse_args()
    if (opt.end - opt.start) != timedelta(days=1):
        p.error('The script processes 24h batches')
    return opt

def main():
    opt = parse_args()
    bucket = opt.start.strftime('%Y-%m-%d')
    meta_pg(opt.autoclaved_root, bucket, opt.postgres)

if __name__ == '__main__':
    main()
