#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import argparse
import collections
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
from canning import isomidnight, dirname

# It does NOT take into account metadata tables right now:
# - autoclaved: it's not obvious if anything can be updated there
# - report & measurement: have significant amount of metadata and may be actually updated eventually
CODE_VER = 3

FLAG_TRUE_TEMP = True # keep temporary tables if the flag is false
FLAG_DEBUG_CHAOS = False # random fault injection
FLAG_FAIL_FAST = False
FLAG_SKIP_SIMHASH = True # it takes 75% of time, disable it for a while 
assert not (FLAG_DEBUG_CHAOS and FLAG_FAIL_FAST), 'Absurd!'

if FLAG_DEBUG_CHAOS:
    import random

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
        s = BAD_UTF8_RE.sub(ur'\ufffd', s).encode('utf-8')
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

def pg_unquote(s):
    if not isinstance(s, basestring):
        raise RuntimeError('Unable to quote unknown type', s)
    if s != '\\N':
        return s.decode('string_escape') # XXX: gone in Python3
    else:
        return None

class PGCopyFrom(object):
    # Write-through buffer for COPY command to be able to COPY to several
    # output tables over single postgres session. Alternative is to use several
    # sessions and pipe data across threads with significant CPU overhead and
    # inability to process every OONI measurement using set of functions to
    # have clean "residual" document after data extraction.
    def __init__(self, pgconn, table, wbufsize=2097152, **kwargs):
        # default chunk size is taken as approx. cwnd between production VMs
        self.__pgconn = pgconn
        self.__table = table
        self.__wbufsize = wbufsize
        self.__kwargs = kwargs
        self.__buf = StringIO()
    def write(self, line):
        assert len(line) == 0 or line[-1] == '\n'
        pos = self.__buf.tell()
        if pos > 0 and pos + len(line) > self.__wbufsize:
            self.flush()
        self.__buf.write(line)
    def flush(self):
        self.__buf.reset()
        with self.__pgconn.cursor() as c:
            try:
                c.copy_from(self.__buf, self.__table, **self.__kwargs)
            except Exception:
                print >>sys.stderr, repr(self.__buf.getvalue())
                raise
        self.__buf.reset()
        self.__buf.truncate()
    def close(self):
        self.flush()
        self.__buf.close()

def get_checked_code_ver(pgconn, autoclaved_index, bucket):
    # Returns:
    #   None -- the bucket was never loaded
    #   int  -- code version stamped in `autoclaved` table for these files
    #
    # Check that postgresql and autoclaved/${bucket}/index.json.gz ...
    # - have same list of data files, names and SHA1 are equal
    # - have same count of reports (type: report) and measurements (type: datum)
    #
    # Number of distinct frames in PG and {type: frame} may differ as there are frames without measurements:
    # $ zcat 2017-03-21/index.json.gz | awk '/"type": ?"frame"/ {a = 0; s = ""} {s = s $0} /"type": ?"datum"/ { a +=1 } (/"type": ?"\/frame"/ && a == 0) {print s; s = ""}' | shuf -n 5
    # {"file_off": 14628392, "file_size": 15, "text_off": 60180480, "text_size": 0, "type": "frame"}{"type": "/frame"}
    # {"file_off": 14508951, "file_size": 74, "text_off": 59792468, "text_size": 9132, "type": "frame"}{"type": "/report"}{"type": "/frame"}
    # {"file_off": 11295485, "file_size": 60, "text_off": 43934392, "text_size": 5448, "type": "frame"}{"type": "/report"}{"type": "/frame"}
    # {"file_off": 9654710, "file_size": 28, "text_off": 41709591, "text_size": 1, "type": "frame"}{"type": "/report"}{"type": "/frame"}
    # {"file_off": 26744767, "file_size": 28, "text_off": 116908344, "text_size": 1, "type": "frame"}{"type": "/report"}{"type": "/frame"}
    #
    # TODO: {type: badblob} is not accounted as it's not currently imported during centrifugation stage.

    files = set()
    report_count, datum_count = 0, 0
    with gzip.GzipFile(autoclaved_index, 'r') as indexfd:
        for _, doc in autoclaving.stream_json_blobs(indexfd):
            doc = ujson.loads(doc)
            t = doc['type']
            if t == 'file':
                filename = doc['filename']
            elif t == '/file':
                files.add((b64decode(doc['file_sha1']), filename))
            elif t == 'report':
                report_count += 1
            elif t == 'datum':
                datum_count += 1

    with pgconn.cursor() as c:
        c.execute('SELECT file_sha1, filename FROM autoclaved WHERE bucket_date = %s', (bucket,))
        files_db = {(str(_[0]), _[1]) for _ in c} # NB: file_sha1 is returned as buffer()
        if files_db == files:
            # that's just a safety check, these tables are commited within single transaction
            c.execute('SELECT COUNT(*) FROM autoclaved JOIN report USING (autoclaved_no) WHERE bucket_date = %s', (bucket,))
            report_db = list(c)[0][0]
            if report_db != report_count:
                raise RuntimeError('Unexpected DB mismatch in report count', bucket, report_count, report_db)
            c.execute('SELECT COUNT(*) FROM autoclaved JOIN report USING (autoclaved_no) JOIN measurement USING (report_no) WHERE bucket_date = %s', (bucket,))
            datum_db = list(c)[0][0]
            if datum_db != datum_count:
                raise RuntimeError('Unexpected DB mismatch in measurement count', bucket, datum_count, datum_db)
            if len(files) != 0:
                c.execute('SELECT MIN(code_ver), MAX(code_ver) FROM autoclaved WHERE bucket_date = %s', (bucket,))
                vermin, vermax = list(c)[0]
            else:
                vermin, vermax = CODE_VER, CODE_VER # as DB will return NULL in this case
            if vermin != vermax:
                raise RuntimeError('Unexpected DB mismatch in code versions', bucket, vermin, vermax)
            return vermin
        elif len(files_db) == 0: # and len(files) > 0 as sets are not equal :)
            return None
        else:
            raise RuntimeError('Unexpected DB mismatch in autoclaved files set', bucket, list(files - files_db)[:5], list(files_db - files)[:5])

def copy_files_from_index(pgconn, autoclaved_index, table, bucket):
    # autoclaved/${bucket}/index.json.gz | filter "type=file" > autoclaved.table
    columns = ('filename', 'bucket_date', 'code_ver', 'file_size', 'file_crc32', 'file_sha1')
    fmt = '{}\t' + bucket + '\t' + str(CODE_VER) + '\t{:d}\t{:d}\t\\\\x{}\n'
    with closing(PGCopyFrom(pgconn, table, columns=columns)) as wbuf, \
        gzip.GzipFile(autoclaved_index, 'r') as indexfd:
        filename = None
        for _, doc in autoclaving.stream_json_blobs(indexfd):
            if 'file"' in doc:
                doc = ujson.loads(doc)
                if doc['type'] == 'file':
                    if filename is not None:
                        raise RuntimeError('Corrupt index file', autoclaved_index, doc)
                    filename = doc['filename']
                elif doc['type'] == '/file':
                    if filename is None:
                        raise RuntimeError('Corrupt index file', autoclaved_index, doc)
                    doc['filename'], filename = filename, None
                    wbuf.write(fmt.format(pg_quote(doc['filename']), doc['file_size'],
                            doc['file_crc32'], b64decode(doc['file_sha1']).encode('hex')))

def copy_reports_from_index(pgconn, autoclaved_index, table, autoclaved_no):
    # autoclaved/${bucket}/index.json.gz | filter "type=report" > report_meta.table
    columns = ('autoclaved_no', 'badtail', 'textname', 'orig_sha1')
    with closing(PGCopyFrom(pgconn, table, columns=columns)) as wbuf, \
        gzip.GzipFile(autoclaved_index, 'r') as indexfd:
        rowno = None
        for _, doc in autoclaving.stream_json_blobs(indexfd):
            if '"datum"' not in doc: # till someone submits report with {"textname":"datum"}...
                doc = ujson.loads(doc)
                t = doc['type']
                if t == 'file':
                    rowno = autoclaved_no[doc['filename']]
                elif t == 'report':
                    report = doc
                elif t == '/report':
                    wbuf.write('{:d}\t{}\t{}\t\\\\x{}\n'.format(rowno, pg_quote(doc.get('src_cutoff')),
                            pg_quote(report['textname']), b64decode(report['orig_sha1']).encode('hex')))

def copy_measurements_from_index(pgconn, autoclaved_index, table, report_no):
    # autoclaved/${bucket}/index.json.gz | filter "type=datum" > measurement_meta.table
    columns = ('report_no', 'frame_off', 'frame_size', 'intra_off', 'intra_size', 'orig_sha1')
    with closing(PGCopyFrom(pgconn, table, columns=columns)) as wbuf, \
        gzip.GzipFile(autoclaved_index, 'r') as indexfd:
        rowno = None
        for _, doc in autoclaving.stream_json_blobs(indexfd):
            doc = ujson.loads(doc)
            t = doc['type']
            if t == 'report':
                rowno = report_no[doc['textname']]
            elif t == '/report':
                rowno = None
            elif t == 'frame':
                frame_off, frame_size, text_off = doc['file_off'], doc['file_size'], doc['text_off']
            elif t == 'datum':
                intra_off = doc['text_off'] - text_off
                wbuf.write('{:d}\t{:d}\t{:d}\t{:d}\t{:d}\t\\\\x{}\n'.format(rowno,
                    frame_off, frame_size, doc['text_off'] - text_off, doc['text_size'],
                    b64decode(doc['orig_sha1']).encode('hex')))
            elif t == 'blob':
                assert False # FIXME: that's some bug, there is no `blob` type AFAIK
                #yield '{:d}\t\\N\t\\N\t\\N\t\\N\t\\\\x{}\n'.format(rowno,
                #    b64decode(doc['orig_sha1']).encode('hex'))

def copy_meta_from_index(pgconn, autoclaved_index, bucket):
    # Writing directly to `report` table is impossible as part of `report`
    # table is parsed from data files, same is true for `measurement` table.
    with pgconn.cursor() as c:
        copy_files_from_index(pgconn, autoclaved_index, 'autoclaved', bucket)
        c.execute('SELECT filename, autoclaved_no FROM autoclaved WHERE bucket_date = %s', [bucket])
        autoclaved_no = dict(c)
        c.execute('CREATE TEMPORARY TABLE report_meta_ (LIKE report_meta INCLUDING ALL) ON COMMIT DROP'
                  if FLAG_TRUE_TEMP else
                  'CREATE TABLE report_meta_ (LIKE report_meta INCLUDING ALL)')
        copy_reports_from_index(pgconn, autoclaved_index, 'report_meta_', autoclaved_no)
        c.execute('SELECT textname, report_no FROM report_meta_')
        report_no = dict(c)
        c.execute('CREATE TEMPORARY TABLE measurement_meta_ (LIKE measurement_meta INCLUDING ALL) ON COMMIT DROP'
                  if FLAG_TRUE_TEMP else
                  'CREATE TABLE measurement_meta_ (LIKE measurement_meta INCLUDING ALL)')
        copy_measurements_from_index(pgconn, autoclaved_index, 'measurement_meta_', report_no)
    return 'report_meta_', 'measurement_meta_'

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

class MeasurementFeeder(object):
    table = 'measurement_blob_'
    columns = ('msm_no', 'measurement_start_time', 'test_runtime', 'id', 'input', 'exc', 'residual')
    def __init__(self, pgconn):
        with pgconn.cursor() as c:
            c.execute(('CREATE TEMPORARY TABLE {} (LIKE measurement_blob INCLUDING ALL) ON COMMIT DROP'
                       if FLAG_TRUE_TEMP else
                       'CREATE TABLE {} (LIKE measurement_blob INCLUDING ALL)'
                      ).format(self.table))
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

class MeasurementExceptionFeeder(object):
    table = 'measurement_exc_'
    columns = ('msm_no', 'exc')
    def __init__(self, pgconn):
        with pgconn.cursor() as c:
            c.execute(('CREATE TEMPORARY TABLE {} (LIKE measurement_exc INCLUDING ALL) ON COMMIT DROP'
                       if FLAG_TRUE_TEMP else
                       'CREATE TABLE {} (LIKE measurement_exc INCLUDING ALL)'
                      ).format(self.table))
    @staticmethod
    def msm_rownpop(msm_no, _, exc):
        if FLAG_DEBUG_CHAOS and random.random() < 0.01:
            raise RuntimeError('bad luck with measurement')
        return '{:d}\t{}\n'.format(msm_no, pg_quote(exc)) if len(exc) else ''

# Python WTF:
# >>> '{}\t{}\t{}\t{}\t{}\t{}\n'.format(1,2,3,4,5,6,7)
# '1\t2\t3\t4\t5\t6\n'
# >>> '%s\t%s\t%s\t%s\t%s\t%s\n' % (1,2,3,4,5,6,7)
# Traceback (most recent call last):
#   File "<stdin>", line 1, in <module>
# TypeError: not all arguments converted during string formatting

class ReportFeeder(object):
    table = 'report_blob_' # it's actually some temporary table
    columns = ('report_no', 'test_start_time', 'probe_cc', 'probe_asn', 'probe_ip', 'test_name',
               'report_id', 'software_no')
    sw_key = ('test_name', 'test_version', 'software_name', 'software_version')
    # common_keys must be same for every measurement in the report file
    common_keys = ('test_start_time', 'probe_cc', 'probe_asn', 'probe_ip', 'report_filename',
       'test_name', 'test_version', 'software_name', 'software_version', 'report_id')
    def __init__(self, pgconn, stconn):
        with pgconn.cursor() as c:
            c.execute(('CREATE TEMPORARY TABLE {} (LIKE report_blob INCLUDING ALL) ON COMMIT DROP'
                       if FLAG_TRUE_TEMP else
                       'CREATE TABLE {} (LIKE report_blob INCLUDING ALL)'
                      ).format(self.table))
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

class BadmetaFeeder(object):
    table = 'badmeta_' # it's actually some temporary table
    columns = ('autoclaved_no', 'report_no', 'textname', 'exc_report', 'exc_measurement')
    def __init__(self, pgconn):
        with pgconn.cursor() as c:
            c.execute(('CREATE TEMPORARY TABLE {} (LIKE badmeta_tpl INCLUDING ALL) ON COMMIT DROP'
                       if FLAG_TRUE_TEMP else
                       'CREATE TABLE {} (LIKE badmeta_tpl INCLUDING ALL)'
                      ).format(self.table))
    @staticmethod
    def badmeta_row(autoclaved_no, report_no, textname, report=None, measurement=None):
        return '{:d}\t{:d}\t{}\t{}\t{}\n'.format(
                autoclaved_no,
                report_no,
                pg_quote(textname),
                pg_quote(exc_hash(report) if report is not None else None),
                pg_quote(exc_hash(measurement) if measurement is not None else None))

IPV4_RE = re.compile(r'^\d+\.\d+\.\d+\.\d+$')

class TcpFeeder(object):
    compat_code_ver = (2, 3)
    table = 'tcp'
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

class DnsFeeder(object):
    compat_code_ver = (2, 3)
    table = 'dns_a_'
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
        with pgconn.cursor() as c:
            c.execute(('CREATE TEMPORARY TABLE {} (LIKE dns_a_tpl INCLUDING ALL) ON COMMIT DROP'
                       if FLAG_TRUE_TEMP else
                       'CREATE TABLE {} (LIKE dns_a_tpl INCLUDING ALL)'
                      ).format(self.table))
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


class BodySimhashSink(object):
    # NB: this data goes to small-transaction connection (stconn) to be
    # available to other nodes as soon as it's commited.
    # Queue is buffered to avoid round-trip to database for every webpage.
    # Computation is delayed till filling the database as it's rather
    # expensive, throughput is ~7.5 Mbytes/s, so roundtrip to DB is done to
    # exclude already parsed pages. It's unclear if extra roundtrip makes sense
    # when known_sha256 cache is used.
    # Average body size is 75kb and cross-report cachehit is ~18%.
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
    def maybe_flush(self):
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

TITLE_REGEXP = re.compile('<title>(.*?)</title>', re.IGNORECASE | re.DOTALL)

def get_title(body):
    if body is None:
        return None
    title = TITLE_REGEXP.search(body)
    if title:
        title = title.group(1).decode('utf-8', 'replace').encode('utf-8')
    return title

class BaseHttpFeeder(object):
    def __init__(self, body_sink):
        self.body_sink = body_sink
    def body_sha256(self, body):
        if body is not None:
            body_sha256 = hashlib.sha256(body)
            self.body_sink.put(body_sha256.digest(), body)
            body_sha256 = '\\\\x' + body_sha256.hexdigest()
        else:
            body_sha256 = pg_quote(None)
        return body_sha256
    COMMON_HEADERS = {
        "Accept-Language": "en-US;q=0.8,en;q=0.5",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36"
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
    compat_code_ver = (2, 3)
    table = 'http_control'
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
                        pg_quote(ujson.dumps(r['headers']))) # seems, empty headers dict is still present it case of failure
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
                        headers = ujson.dumps(headers)
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
    compat_code_ver = (2, 3)
    table = 'http_request'
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
            headers = ujson.dumps(headers)
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
    compat_code_ver = (3,)
    table = 'http_request_fp'
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

class HttpVerdictFeeder(object):
    compat_code_ver = (2, 3)
    table = 'http_verdict'
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

def meta_pg_blobtable(stream_cls, dsn, queue, table, schema_table):
    with closing(psycopg2.connect(dsn=dsn)) as conn:
        with conn, conn.cursor() as c:
            # FIXME: create accurate template tables and do `INCLUDING ALL` ?
            c.execute('CREATE UNLOGGED TABLE IF NOT EXISTS {} '
                      '(LIKE {} INCLUDING DEFAULTS INCLUDING INDEXES)'.format(table, schema_table))
            c.execute('TRUNCATE TABLE {}'.format(table))
            source = stream_cls(dsn, queue)
            c.copy_from(source, table, columns=source.columns)

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
        autoclaved_index = os.path.join(in_root, bucket, autoclaving.INDEX_FNAME)
        code_ver = get_checked_code_ver(pgconn, autoclaved_index, bucket)
        if code_ver is None:
            meta_tables = copy_meta_from_index(pgconn, autoclaved_index, bucket)
        elif CODE_VER == code_ver:
            print 'public/autoclaved and postgres are in sync, bucket={}, code_ver={}'.format(bucket, code_ver)
            return
        elif CODE_VER < code_ver:
            raise RuntimeError('Unable to run old centrifugation with new postgres', CODE_VER, code_ver)
        else:
            assert code_ver < CODE_VER
            #assert not FLAG_DEBUG_CHAOS # to avoid accidental chaotic update of production DB
            meta_tables = 'report', 'measurement'
        # TODO: check if table should be feeded with `row` or just skipped

        body_sink = BodySimhashSink(stconn)
        badmeta_feeder = BadmetaFeeder(pgconn)
        badmeta_sink = PGCopyFrom(pgconn, badmeta_feeder.table, columns=badmeta_feeder.columns)
        if code_ver is None:
            report_feeder = ReportFeeder(pgconn, stconn)
            report_sink = PGCopyFrom(pgconn, report_feeder.table, columns=report_feeder.columns)
            msm_feeder = MeasurementFeeder(pgconn)
        else:
            msm_feeder = MeasurementExceptionFeeder(pgconn)
        msm_sink = PGCopyFrom(pgconn, msm_feeder.table, columns=msm_feeder.columns)

        data_tables = (
            (TcpFeeder, ()),
            (DnsFeeder, (pgconn,)),
            (HttpRequestFeeder, (body_sink,)),
            (HttpRequestFPFeeder, (pgconn,)),
            (HttpControlFeeder, (body_sink,)),
            (HttpVerdictFeeder, ()),
        )
        row_handlers = []
        for cls, args in data_tables:
            assert CODE_VER in cls.compat_code_ver, (CODE_VER, cls.compat_code_ver, cls.table)
            if code_ver not in cls.compat_code_ver:
                # this table should be updated
                feeder = cls(*args)
                sink = PGCopyFrom(pgconn, cls.table, columns=cls.columns)
                row_handlers.append((feeder, sink))
        assert len(row_handlers), "No tables should be updated"

        if code_ver is not None: # that's update, not initial insert
            c.execute('''
                CREATE TEMPORARY TABLE bktmsm AS
                SELECT msm_no
                FROM autoclaved JOIN {} USING (autoclaved_no) JOIN {} USING (report_no)
                WHERE bucket_date = %s
            '''.format(*meta_tables), [bucket])
            c.execute('ANALYSE bktmsm') # to improve plan a bit
            for feeder, _ in row_handlers:
                c.execute('DELETE FROM {} WHERE msm_no IN (SELECT msm_no FROM bktmsm)'.format(
                    feeder.table))
            c.execute('DROP TABLE bktmsm') # clean-up early

        sink_handlers = [_[1] for _ in row_handlers] + [body_sink, badmeta_sink, msm_sink]
        if code_ver is None:
            # NB: report_feeder is last pop_handlers and there are no pop_handlers for `UPDATE` !
            pop_handlers = [_[0] for _ in row_handlers] + [report_feeder]
            sink_handlers.append(report_sink)

        TrappedException = None if FLAG_FAIL_FAST else Exception

        # The query to fetch LZ4 metadata for files takes ~256 bytes per row if all
        # the data is fetched in the memory of this process, 2014-11-22 has ~1e6
        # measurements so server-side cursor is used as a safety net against OOM.
        with pgconn.cursor('lz4meta') as cmeta:
            cmeta.itersize = 2*1024**2 / 256
            cmeta.execute('''
                SELECT filename, frame_off, frame_size, intra_off, intra_size,
                       report_no, msm_no, autoclaved_no, textname
                FROM autoclaved JOIN {} USING (autoclaved_no) JOIN {} USING (report_no)
                WHERE bucket_date = %s
                ORDER BY filename, frame_off, intra_off'''.format(*meta_tables),
                [bucket])
            for filename, itfile in groupby(cmeta, itemgetter(0)):
                print filename
                with open(os.path.join(in_root, filename)) as fd:
                    for (frame_off, frame_size), itframe in groupby(itfile, itemgetter(1, 2)):
                        assert fd.tell() == frame_off
                        blob = fd.read(frame_size)
                        assert len(blob) == frame_size
                        blob = lz4frame.decompress(blob)
                        for filename, frame_off, frame_size, intra_off, intra_size, report_no, msm_no, autoclaved_no, textname in itframe:
                            datum = blob[intra_off:intra_off+intra_size]
                            assert len(datum) == intra_size
                            datum = ujson.loads(datum)

                            queue, exc = [], []
                            if code_ver is None:
                                try:
                                    row = report_feeder.report_row(report_no, datum)
                                except TrappedException:
                                    badmeta_sink.write(badmeta_feeder.badmeta_row(
                                        autoclaved_no, report_no, textname, report=sys.exc_info()))
                                    continue # skip measurement with bad metadata
                                else:
                                    queue.append((report_sink, row))

                            for feeder, sink in row_handlers:
                                try:
                                    if FLAG_DEBUG_CHAOS and random.random() < 0.01:
                                        raise RuntimeError('bad luck with ordinary feeder')
                                    row = feeder.row(msm_no, datum)
                                except TrappedException:
                                    exc.append(exc_hash(sys.exc_info()))
                                else:
                                    queue.append((sink, row))

                            if code_ver is None:
                                for feeder in pop_handlers:
                                    try:
                                        feeder.pop(datum)
                                        # chaos is injected after pop() to avoid `residual` table pollution
                                        if FLAG_DEBUG_CHAOS and random.random() < 0.01:
                                            raise RuntimeError('bad luck with feeder.pop')
                                    except TrappedException:
                                        exc.append(exc_hash(sys.exc_info()))

                            try:
                                row = msm_feeder.msm_rownpop(msm_no, datum, exc)
                            except TrappedException:
                                badmeta_sink.write(badmeta_feeder.badmeta_row(
                                    autoclaved_no, report_no, textname, measurement=sys.exc_info()))
                                continue # skip measurement with bad metadata
                            else:
                                queue.append((msm_sink, row))

                            for sink, row in queue:
                                sink.write(row)
                            body_sink.maybe_flush()
        for sink in sink_handlers:
            sink.close()
        # Okay, server-side cursor feeding indexes is closed and the code is
        # still alive, it's time to morph temporary tables!
        if code_ver is None:
            c.execute('''
                INSERT INTO report
                SELECT report_no, autoclaved_no, test_start_time, probe_cc, probe_asn, probe_ip,
                       test_name, badtail, textname, orig_sha1,
                       COALESCE(report_id, translate(encode(orig_sha1, 'base64'), '/+=', '_-')), software_no
                FROM report_meta_
                JOIN report_blob_ USING (report_no)
            ''') # TODO: `LEFT JOIN report_blob_` to fail fast in case of errors
            c.execute('''
                INSERT INTO input (input)
                SELECT DISTINCT input FROM measurement_blob_ WHERE input IS NOT NULL
                ON CONFLICT DO NOTHING
            ''')
            c.execute('''
                INSERT INTO residual (residual)
                SELECT DISTINCT residual FROM measurement_blob_
                ON CONFLICT DO NOTHING
            ''')
            c.execute('''
                INSERT INTO measurement
                SELECT msm_no, report_no, frame_off, frame_size, intra_off, intra_size,
                measurement_start_time, test_runtime, orig_sha1, id, input_no, exc, residual_no
                FROM measurement_meta_
                JOIN measurement_blob_ USING (msm_no)
                LEFT JOIN input USING (input)
                LEFT JOIN residual USING (residual)
            ''') # TODO: `LEFT JOIN measurement_blob_` to fail fast
        else:
            c.execute('''
                UPDATE measurement msm
                SET exc = array_append(msm.exc, NULL) || mex.exc
                FROM measurement_exc_ mex
                WHERE mex.msm_no = msm.msm_no
            ''', [CODE_VER])
            c.execute('''
                UPDATE autoclaved
                SET code_ver = %s
                WHERE bucket_date = %s
            ''', [CODE_VER, bucket])
        if any(_[0].table == 'dns_a_' for _ in row_handlers):
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
        else:
            print "No updates for dns_a_ table"
        c.execute('''
            INSERT INTO badmeta
            SELECT
                badmeta_.autoclaved_no,
                badmeta_.report_no,
                CASE WHEN report.report_no IS NULL THEN badmeta_.textname ELSE NULL END,
                COALESCE(array_agg(exc_report) FILTER (WHERE exc_report IS NOT NULL), ARRAY[]::int4[]),
                COALESCE(array_agg(exc_measurement) FILTER (WHERE exc_measurement IS NOT NULL), ARRAY[]::int4[])
            FROM badmeta_
            LEFT JOIN report USING (report_no)
            GROUP BY badmeta_.autoclaved_no, badmeta_.report_no, badmeta_.textname, report.report_no
        ''')
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
