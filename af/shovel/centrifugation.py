#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import argparse
import base64
import collections
import gzip
import itertools
import numbers
import os
import re
import sys
import tempfile
import traceback
import threading
import Queue
from base64 import b64decode
from contextlib import closing, contextmanager
from datetime import timedelta
from functools import partial
from itertools import groupby
from operator import itemgetter

import lz4.frame as lz4frame
import mmh3
import psycopg2
import simhash
import ujson

import autoclaving
from canning import isomidnight, dirname, Future

CODE_VER = 2

class LZ4WriteStream(object):
    def __init__(self, fileobj):
        self.__file = fileobj
        self.__ctx = lz4frame.create_compression_context()
        self.__file.write(lz4frame.compress_begin(self.__ctx,
                    block_size=lz4frame.BLOCKSIZE_MAX4MB, # makes no harm for larger blobs
                    block_mode=lz4frame.BLOCKMODE_LINKED,
                    compression_level=5,
                    content_checksum=lz4frame.CONTENTCHECKSUM_ENABLED,
                    # sorry, no per-block checksums yet
                    auto_flush=False))

    def write(self, blob):
        self.__file.write(lz4frame.compress_update(self.__ctx, blob))

    def close(self):
        self.__file.write(lz4frame.compress_end(self.__ctx))
        self.__file.flush()
        del self.__ctx, self.__file

WORD_RE = re.compile('''[^\t\n\x0b\x0c\r !"#$%&\'()*+,-./:;<=>?@[\\\\\\]^_`{|}~']+''')

def sim_shi4_mm3(text):
    i1, i2 = itertools.tee(WORD_RE.finditer(text))
    for _ in xrange(3): # 4 words per shingle
        next(i2, None)
    mm = [mmh3.hash64(text[m1.start():m2.end()]) for m1, m2 in itertools.izip(i1, i2)]
    return (simhash.compute([_[0] & 0xffffffffffffffff for _ in mm]),
            simhash.compute([_[1] & 0xffffffffffffffff for _ in mm]))

AUTOCLAVED_RE = re.compile(r'^\d{4}-[0-1][0-9]-[0-3][0-9]/(?:\d{4}[0-1][0-9][0-3][0-9]T[0-2][0-9][0-5][0-9][0-5][0-9]Z-[A-Z]{2}-AS\d+-(?P<test_name_1>[^-]+)-[^-]+-[.0-9]+-probe\.(?:yaml|json)|(?P<test_name_2>[^-]+)\.\d+\.tar)\.lz4$')

def autoclaved_test_name(x):
    m = AUTOCLAVED_RE.match(x)
    if m is None:
        raise RuntimeError('Bad name for autoclaved file', x)
    name1, name2 = m.groups()
    return name1 or name2

FILE_START, FILE_END, REPORT_START, REPORT_END, BADBLOB, DATUM = object(), object(), object(), object(), object(), object()

def stream_datum(atclv_root, bucket, take_file=None):
    with gzip.GzipFile(os.path.join(atclv_root, bucket, autoclaving.INDEX_FNAME), 'r') as indexfd:
        filefd = None
        dociter = autoclaving.stream_json_blobs(indexfd)
        for _, doc in dociter:
            doc = ujson.loads(doc)
            t = doc['type']
            if t == 'datum':
                # {"orig_sha1": "q7…I=", "text_off": 156846, "text_size": 58327, "type": "datum"}
                intra_off = doc['text_off'] - text_off
                datum = blob[intra_off:intra_off+doc['text_size']]
                assert intra_off >= 0 and len(datum) == doc['text_size']
                datum = ujson.loads(datum)
                doc['frame_off'] = frame_off
                doc['frame_size'] = frame_size
                doc['intra_off'] = intra_off
                doc['intra_size'] = doc['text_size']
                doc['datum'] = datum
                yield DATUM, doc
                del intra_off, datum

            elif t == 'frame':
                # {"file_off": 0, "file_size": 162864, "text_off": 0, "text_size": 362462, … }
                frame_off, frame_size = doc['file_off'], doc['file_size']
                assert filefd.tell() == frame_off
                blob = filefd.read(frame_size)
                assert len(blob) == frame_size
                blob = lz4frame.decompress(blob)
                assert len(blob) == doc['text_size']
                text_off = doc['text_off']

            elif t == '/frame':
                del frame_off, frame_size, text_off, blob

            elif t == 'report':
                # {"orig_sha1": "HO…U=",
                #  "src_size": 104006450,
                #  "textname": "2017-01-01/20161231T000030Z-US-AS…-0.2.0-probe.json", …}
                yield REPORT_START, doc

            elif t == '/report':
                # {"info": "<class '__main__.TruncatedReportError'>",
                #  "src_cutoff": 49484700, … }
                yield REPORT_END, doc

            elif t == 'file':
                # {"filename": "2017-01-01/20161231T000030Z-US-AS…-0.2.0-probe.json.lz4", …}
                filename = doc['filename']
                assert filename.startswith(bucket)
                if take_file is None or take_file(filename):
                    filefd = open(os.path.join(atclv_root, filename), 'rb')
                    del filename
                    yield FILE_START, doc
                else:
                    for _, skipdoc in dociter:
                        if '/file"' in skipdoc and ujson.loads(skipdoc)['type'] == '/file':
                            break
                    del filename, skipdoc

            elif t == '/file':
                # {"file_crc32": -156566611, "file_sha1": "q/…8=", "file_size": 18132131, …}
                assert filefd.tell() == doc['file_size']
                filefd.close()
                filefd = None
                yield FILE_END, doc

            elif t == 'badblob':
                # {"orig_sha1": "RXQFwOtpKtS0KicYi8JnWeQYYBw=",
                #  "src_off": 99257, "src_size": 238,
                #  "info": "<class 'yaml.constructor.ConstructorError'>", …}
                yield BADBLOB, doc

            else:
                raise RuntimeError('Unknown record type', t)
        if filefd is not None:
            raise RuntimeError('Truncated autoclaved index', atclv_root, bucket)

CHUNK_RE = re.compile('\x0d\x0a([0-9a-f]+)\x0d\x0a')

def httpt_body(response):
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
            if k.lower() == 'transfer-encoding' and v == 'chunked':
                break
        else:
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

def simhash_text_to_fd(datum_iter, outfd):
    for ev, doc in datum_iter:
        assert ev is FILE_START
        autoclaved = doc
        for ev, doc in datum_iter:
            if ev is FILE_END:
                break
            assert ev is REPORT_START
            report = doc
            for ev, doc in datum_iter:
                if ev is DATUM:
                    try:
                        for req in doc['datum']['test_keys']['requests']:
                            if not req['request']['tor']['is_tor'] and req['response'] and req['response']['body']:
                                body = httpt_body(req['response'])
                                if body:
                                    h1, h2 = sim_shi4_mm3(body)
                                    print >>outfd, report['orig_sha1'], doc['orig_sha1'], req['request']['url'], h1, h2
                    except Exception:
                        pass # req
                elif ev is BADBLOB:
                    pass
                elif ev is REPORT_END:
                    break
                else:
                    raise RuntimeError('Unexpected event type', doc['type'])
            assert ev is REPORT_END
        assert ev is FILE_END

def simhash_text(in_root, out_root, bucket):
    assert in_root[-1] != '/' and out_root[-1] != '/' and '/' not in bucket
    in_dir = os.path.join(in_root, bucket)
    assert os.path.isdir(in_dir) and os.path.isdir(out_root)

    simhash_fpath = os.path.join(out_root, bucket + '.simhash.lz4')
    if os.path.exists(simhash_fpath):
        print 'The bucket {} has simhash already built'.format(bucket)
        return

    with tempfile.NamedTemporaryFile(prefix='tmpsim', dir=out_root) as rawfd:
        with closing(LZ4WriteStream(rawfd)) as fd:
            simhash_text_to_fd(
                stream_datum(
                    in_root,
                    bucket,
                    lambda x: autoclaved_test_name(x) in ('web_connectivity', 'http_requests')),
                fd)
        os.link(rawfd.name, simhash_fpath)
    os.chmod(simhash_fpath, 0444)

########################################################################

class PostgresSource(object):
    # NB: Delimiter is always TAB!
    def __init__(self, *args, **kwargs):
        self.__buf = None
        if args or kwargs:
            self._tsv_iter = self._iter(*args, **kwargs)

    def read(self, sz):
        if self.__buf:
            ret, self.__buf = self.__buf, None
        else:
            ret = ''
        while len(ret) < sz:
            chunk = self._readline()
            if not chunk:
                break
            ret += chunk
        if len(ret) > sz:
            ret, self.__buf = ret[:sz], ret[sz:]
        return ret

    def readline(self):
        if self.__buf:
            assert self.__buf[-1] == '\n'
            ret, self.__buf = self.__buf, None
            return ret
        return self._readline()

    @staticmethod
    def _quote(s):
        # The following characters must be preceded by a backslash if they
        # appear as part of a column value: backslash itself, newline, carriage
        # return, and the current delimiter character.
        # -- https://www.postgresql.org/docs/9.6/static/sql-copy.html
        if isinstance(s, basestring):
            return s.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        elif s is None:
            return '\\N'
        elif isinstance(s, bool): # WTF: assert isinstance(True, numbers.Number)!
            return 'TRUE' if s else 'FALSE'
        elif isinstance(s, numbers.Number):
            return s
        else:
            raise RuntimeError('Unable to quote unknown type', s)

    @staticmethod
    def _unquote(s):
        if not isinstance(s, basestring):
            raise RuntimeError('Unable to quote unknown type', s)
        if s != '\\N':
            return s.decode('string_escape') # XXX: gone in Python3
        else:
            return None

    def _readline(self):
        return next(self._tsv_iter, '')

class AutoclavedMetadataStream(PostgresSource):
    columns = ('filename', 'bucket_date', 'code_ver', 'file_size', 'file_crc32', 'file_sha1')
    def __init__(self, atclv_index, bucket):
        PostgresSource.__init__(self)
        fmt = '{}\t' + bucket + '\t' + str(CODE_VER) + '\t{:d}\t{:d}\t\\\\x{}\n'
        self._tsv_iter = self.__iter(atclv_index, fmt)
    @staticmethod
    def __iter(atclv_index, fmt):
        with gzip.GzipFile(atclv_index, 'r') as indexfd:
            filename = None
            for _, doc in autoclaving.stream_json_blobs(indexfd):
                if 'file"' in doc:
                    doc = ujson.loads(doc)
                    if doc['type'] == 'file':
                        if filename is not None:
                            raise RuntimeError('Corrupt index file', index_fpath, doc)
                        filename = doc['filename']
                    elif doc['type'] == '/file':
                        if filename is None:
                            raise RuntimeError('Corrupt index file', index_fpath, doc)
                        doc['filename'], filename = filename, None
                        yield fmt.format(PostgresSource._quote(doc['filename']), doc['file_size'],
                                doc['file_crc32'], b64decode(doc['file_sha1']).encode('hex'))

class ReportMetadataStream(PostgresSource):
    columns = ('autoclaved_no', 'badtail', 'textname', 'orig_sha1')
    @staticmethod
    def _iter(atclv_index, autoclaved_no):
        _quote = PostgresSource._quote
        with gzip.GzipFile(atclv_index, 'r') as indexfd:
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
                        yield '{:d}\t{}\t{}\t\\\\x{}\n'.format(rowno, _quote(doc.get('src_cutoff')),
                                _quote(report['textname']), b64decode(report['orig_sha1']).encode('hex'))

class MeasurementMetadataStream(PostgresSource):
    columns = ('report_no', 'frame_off', 'frame_size', 'intra_off', 'intra_size', 'orig_sha1')
    @staticmethod
    def _iter(atclv_index, report_no):
        with gzip.GzipFile(atclv_index, 'r') as indexfd:
            rowno = None
            for _, doc in autoclaving.stream_json_blobs(indexfd):
                doc = ujson.loads(doc)
                t = doc['type']
                if t == 'report':
                    rowno = report_no[doc['textname']]
                elif t == 'frame':
                    frame_off, frame_size, text_off = doc['file_off'], doc['file_size'], doc['text_off']
                elif t == 'datum':
                    intra_off = doc['text_off'] - text_off
                    yield '{:d}\t{:d}\t{:d}\t{:d}\t{:d}\t\\\\x{}\n'.format(rowno,
                        frame_off, frame_size, doc['text_off'] - text_off, doc['text_size'],
                        b64decode(doc['orig_sha1']).encode('hex'))
                elif t == 'blob':
                    yield '{:d}\t\\N\t\\N\t\\N\t\\N\t\\\\x{}\n'.format(rowno,
                        b64decode(doc['orig_sha1']).encode('hex'))

class IterableQueue(object):
    __END = object()
    def __init__(self, *args, **kwargs):
        self.__closed = False
        self.__drained = False
        self.__reader = None
        self.__writer = None
        self.__q = Queue.Queue(*args, **kwargs)
        self.__broken = threading.Event() # instead of atomic bool
    def __iter__(self):
        assert self.__reader is None
        self.__reader = threading.current_thread()
        return self
    def next(self): # __next__ in python3
        assert self.__reader is threading.current_thread()
        if self.__drained:
            raise StopIteration # WTF: why is .next() called after StopIteration being thrown?
        item = self.__q.get()
        if item is not self.__END:
            return item
        self.__drained = True
        raise StopIteration
    def put(self, obj):
        if self.__writer is None:
            self.__writer = threading.current_thread()
        assert self.__writer is threading.current_thread()
        if self.__broken.is_set():
            raise RuntimeError('Broken pipe IterableQueue')
        self.__q.put(obj)
    def drain(self):
        self.__broken.set()
        for _ in self:
            pass
    def close(self): # signal EOF
        assert self.__writer is None or self.__writer is threading.current_thread()
        if not self.__closed:
            self.__closed = True
            self.__q.put(self.__END)

class MeasurementStream(PostgresSource):
    columns = ('msm_no', 'measurement_start_time', 'test_runtime', 'id', 'input_no')
    @staticmethod
    def _iter(dsn, queue):
        _quote = PostgresSource._quote
        with closing(psycopg2.connect(dsn)) as cacheconn:
            input_no = PostgresDict(cacheconn, 'input', 'input_no', ('input',))
            for report_no, msm_no, datum in queue:
                input_txt = datum['input'] # may be `list`
                if datum['test_name'] == 'meek_fronted_requests_test':
                    input_txt = '{}:{}'.format(*input_txt)
                elif datum['test_name'] == 'tls_handshake':
                    input_txt = '{}:{:d}'.format(*input_txt)
                assert isinstance(input_txt, (type(None), basestring)), 'Unexpected input {}'.format(repr(input_txt))
                rowno = input_no[input_txt] if input_txt is not None else None
                yield '{:d}\t{}\t{}\t{}\t{}\n'.format(msm_no,
                            _quote(datum['measurement_start_time']), # nullable
                            _quote(datum['test_runtime']), # nullable
                            _quote(datum['id']),
                            _quote(rowno))

class ReportStream(PostgresSource):
    columns = ('report_no', 'test_start_time', 'probe_cc', 'probe_asn', 'probe_ip', 'test_name',
               'report_id', 'software_no')
    @staticmethod
    def _iter(dsn, queue):
        _quote = PostgresSource._quote
        common_keys = ('test_start_time', 'probe_cc', 'probe_asn', 'probe_ip', 'report_filename',
                       'test_name', 'test_version', 'software_name', 'software_version', 'report_id')
        with closing(psycopg2.connect(dsn)) as cacheconn:
            with cacheconn.cursor() as c:
                c.execute('SELECT unnest(enum_range(NULL::ootest))')
                ootest_enum = {_[0] for _ in c.fetchall()}
            sw_key = ('test_name', 'test_version', 'software_name', 'software_version')
            software_no = PostgresDict(cacheconn, 'software', 'software_no', sw_key)
            for report_no, repit in itertools.groupby(queue, itemgetter(0)):
                report_no, msm_no, datum = next(repit)
                rr = {key: datum[key] for key in common_keys} # Report Record
                for _, _, datum in repit:
                    for key in common_keys:
                        if datum[key] != rr[key]:
                            raise RuntimeError('rr key mismatch', key, rr, datum[key])
                rr['software_no'] = software_no[tuple(rr[_] for _ in sw_key)] # before touching `test_name`
                if rr['probe_asn'][:2] != 'AS':
                    raise RuntimeError('Bad AS number', rr['probe_asn'])
                rr['probe_asn'] = int(rr['probe_asn'][2:])
                if rr['probe_ip'] == '127.0.0.1':
                    rr['probe_ip'] = None
                if rr['test_name'] not in ootest_enum:
                    rr['test_name'] = None
                if not rr['report_id']:
                    rr['report_id'] = None
                yield '{:d}\t{}\t{}\t{:d}\t{}\t{}\t{}\t{:d}\n'.format(report_no, rr['test_start_time'],
                        rr['probe_cc'], rr['probe_asn'], _quote(rr['probe_ip']), _quote(rr['test_name']),
                        _quote(rr['report_id']), rr['software_no'])

IPV4_RE = re.compile(r'^\d+\.\d+\.\d+\.\d+$')

class TcpStream(PostgresSource):
    columns = ('msm_no', 'ip', 'port', 'control_failure', 'test_failure')
    @staticmethod
    def _iter(dsn_unused, queue):
        _quote = PostgresSource._quote
        for _, msm_no, datum in queue:
            try:
                tcp = []
                for el in datum['test_keys'].get('tcp_connect', ()):
                    ip, port, test = el['ip'], el['port'], el['status']['failure']
                    if IPV4_RE.match(ip): # domains?! why?!
                        ipport = '{}:{:d}'.format(ip, port)
                        control = datum['test_keys'].get('control', {}).get('tcp_connect', {}).get(ipport)
                        if control:
                            control = control['failure']
                            tcp.append('{:d}\t{}\t{:d}\t{}\t{}\n'.format(msm_no, ip, port,
                                                 _quote(control), _quote(test)))
                for _ in tcp:
                    yield _
            except Exception:
                pass

class DnsStream(PostgresSource):
    columns = ('msm_no', 'domain_no', 'control_ip', 'test_ip')
    @staticmethod
    def _iter(dsn, queue):
        _quote = PostgresSource._quote
        with closing(psycopg2.connect(dsn)) as cacheconn:
            domain_no = PostgresDict(cacheconn, 'domain', 'domain_no', ('domain',))
            for _, msm_no, datum in queue:
                try:
                    test = {}
                    for el in datum['test_keys'].get('queries', ()):
                        if el['query_type'] == 'A':
                            hostname = el['hostname']
                            for ans in el['answers']:
                                if ans['answer_type'] == 'A':
                                    test.setdefault(hostname, set()).add(ans['ipv4'])
                    if len(test) != 1:
                        continue
                    control = filter(IPV4_RE.match, datum['test_keys']['control']['dns']['addrs'])
                    domain = test.keys()[0].rstrip('.')
                    rowno = domain_no[domain]
                    test = ','.join(sorted(test[domain]))
                    control = ','.join(sorted(control))
                    if test and control:
                        # FIXME: test & control failures
                        yield '{:d}\t{:d}\t{{{}}}\t{{{}}}\n'.format(msm_no, rowno, control, test)
                except Exception:
                    pass

TITLE_REGEXP = re.compile('<title>(.*?)</title>', re.IGNORECASE | re.DOTALL)

def get_title(body):
    if body is None:
        return None
    title = TITLE_REGEXP.search(body)
    if title:
        title = title.group(1).decode('utf-8', 'replace').encode('utf-8')
    return title

class HttpControlStream(PostgresSource):
    columns = ('msm_no', 'is_tor', 'failure', 'status_code', 'body_length', 'title', 'headers')
    @staticmethod
    def _iter(dsn_unused, queue):
        _quote = PostgresSource._quote
        for _, msm_no, datum in queue:
            try:
                r = datum['test_keys']['control']['http_request']
                yield '{:d}\tfalse\t{}\t{}\t{}\t{}\t{}\n'.format(msm_no, _quote(r['failure']),
                        _quote(r['status_code']), _quote(r['body_length']), _quote(r['title']),
                        _quote(ujson.dumps(r['headers'])))
            except Exception:
                pass
            try:
                for r in datum['test_keys']['requests']:
                    if r['request']['tor']['is_tor']:
                        rr = r['response']
                        body = httpt_body(rr)
                        yield '{:d}\ttrue\t{}\t{}\t{}\t{}\t{}\n'.format(msm_no, _quote(r['failure']),
                                _quote(rr['code']),
                                _quote(len(body) if body is not None else None),
                                _quote(get_title(body)),
                                _quote(ujson.dumps(rr['headers'])))
            except Exception:
                pass

class HttpRequestStream(PostgresSource):
    columns = ('msm_no', 'url', 'failure', 'status_code', 'body_length', 'title', 'headers')
    @staticmethod
    def _iter(dsn_unused, queue):
        _quote = PostgresSource._quote
        for _, msm_no, datum in queue:
            try:
                for r in datum['test_keys']['requests']:
                    if not r['request']['tor']['is_tor']:
                        rr = r['response']
                        body = httpt_body(rr)
                        yield '{:d}\t{}\t{}\t{}\t{}\t{}\t{}\n'.format(msm_no,
                                _quote(r['request']['url']),
                                _quote(r['failure']),
                                _quote(rr['code']),
                                _quote(len(body) if body is not None else None),
                                _quote(get_title(body)),
                                _quote(ujson.dumps(rr['headers'])))
            except Exception:
                pass

class HttpVerdictStream(PostgresSource):
    columns = ('msm_no', 'accessible', 'control_failure', 'http_experiment_failure', 'title_match',
               'dns_consistency', 'dns_experiment_failure', 'body_proportion', 'blocking',
               'body_length_match', 'headers_match', 'status_code_match')
    @staticmethod
    def _iter(dsn_unused, queue):
        _quote = PostgresSource._quote
        keys = HttpVerdictStream.columns[1:]
        blndx = keys.index('blocking') # may be BOTH bolean and text, needs some type convertion
        fmt = '{:d}\t' + '\t'.join(['{}'] * len(keys)) + '\n'
        for _, msm_no, datum in queue:
            row = [datum['test_keys'].get(_) for _ in keys]
            if isinstance(row[blndx], bool):
                row[blndx] = 'true' if row[blndx] else 'false' # enfoce string type
            yield fmt.format(msm_no, *map(_quote, row))

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
    def __init__(self, conn, table, value, key):
        collections.defaultdict.__init__(self)
        self.__conn = conn
        # Ouch, really ugly
        with self.__conn, conn.cursor() as c:
            c.execute('SELECT {}, {} FROM {}'.format(value, ', '.join(key), table))
            for _ in c:
                self[_[1:]] = _[0]
        self.__select = 'SELECT {} FROM {} WHERE '.format(value, table) + ' AND '.join(_+' = %s' for _ in key)
        self.__insert = 'INSERT INTO {} ({}) VALUES({}) ON CONFLICT DO NOTHING RETURNING {}'.format(table, ', '.join(key),
                            ', '.join(['%s']*len(key)), value)
    def __missing__(self, key):
        with self.__conn, self.__conn.cursor() as c:
            dbkey = (key,) if isinstance(key, basestring) else key
            c.execute(self.__insert, dbkey)
            row = c.fetchone()
            if row is None:
                c.execute(self.__select, dbkey)
                row = c.fetchone()
            self[key] = row[0]
            return self[key]

def meta_pg_metatable(c, bckt, in_root, bucket):
    atclv_index = os.path.join(in_root, bucket, autoclaving.INDEX_FNAME)

    # Well, autoclaved_YYYYMMDD table is not required, but it makes things more transactional.

    c.execute('CREATE UNLOGGED TABLE IF NOT EXISTS autoclaved_meta{} (LIKE autoclaved INCLUDING ALL)'.format(bckt))
    c.execute('CREATE UNLOGGED TABLE IF NOT EXISTS report_meta{} (LIKE report_meta INCLUDING ALL)'.format(bckt))
    c.execute('CREATE UNLOGGED TABLE IF NOT EXISTS measurement_meta{} (LIKE measurement_meta INCLUDING ALL)'.format(bckt))
    c.execute('TRUNCATE TABLE autoclaved_meta{}'.format(bckt))
    c.execute('TRUNCATE TABLE report_meta{}'.format(bckt))
    c.execute('TRUNCATE TABLE measurement_meta{}'.format(bckt))

    source = AutoclavedMetadataStream(atclv_index, bucket)
    c.copy_from(source, 'autoclaved_meta'+bckt, columns=source.columns)
    c.execute('SELECT filename, autoclaved_no FROM autoclaved_meta{}'.format(bckt))
    autoclaved_no = dict(c.fetchall())

    source = ReportMetadataStream(atclv_index, autoclaved_no)
    del autoclaved_no
    c.copy_from(source, 'report_meta'+bckt, columns=source.columns)
    c.execute('SELECT textname, report_no FROM report_meta{}'.format(bckt))
    report_no = dict(c.fetchall())

    source = MeasurementMetadataStream(atclv_index, report_no)
    c.copy_from(source, 'measurement_meta'+bckt, columns=source.columns)

def meta_pg(in_root, bucket, postgres):
    assert in_root[-1] != '/' and '/' not in bucket and os.path.isdir(os.path.join(in_root, bucket))

    # 1. Tables use bucket suffix to allow concurrent workers filling different tables.
    # 2. Tables do NOT include random string in the suffix (like timestamp) to
    # avoid filling the disk with bad retries.  3. Tables are `UNLOGGED` and not
    # `TEMPORARY` as these tables may be shared across different sessions: DNS
    # metadata and TCP metadata are processed with COPY to different tables.

    conn = psycopg2.connect(dsn=postgres)
    bckt = bucket.translate(None, '-') # YYYY-MM-DD -> YYYYMMDD

    with conn, conn.cursor() as c, \
         closing(IterableQueue(128)) as qreport, \
         closing(IterableQueue(128)) as qmsm, \
         closing(IterableQueue(128)) as qtcp, \
         closing(IterableQueue(128)) as qdns, \
         closing(IterableQueue(128)) as qhttpctrl, \
         closing(IterableQueue(128)) as qhttpreq, \
         closing(IterableQueue(128)) as qhttpjudge:

        meta_pg_metatable(c, bckt, in_root, bucket)

        futures = (
            Future(qreport.drain, meta_pg_blobtable,
                   ReportStream, postgres, qreport, 'report_blob'+bckt, 'report_blob'),
            Future(qreport.drain, meta_pg_blobtable,
                   MeasurementStream, postgres, qmsm, 'measurement_blob'+bckt, 'measurement_blob'),
            Future(qreport.drain, meta_pg_blobtable, TcpStream, postgres, qtcp, 'tcp'+bckt, 'tcp'),
            Future(qreport.drain, meta_pg_blobtable, DnsStream, postgres, qdns, 'dns_a'+bckt, 'dns_a'),
            Future(qreport.drain, meta_pg_blobtable,
                   HttpControlStream, postgres, qhttpctrl, 'http_control'+bckt, 'http_control'),
            Future(qreport.drain, meta_pg_blobtable,
                   HttpRequestStream, postgres, qhttpreq, 'http_request'+bckt, 'http_request'),
            Future(qreport.drain, meta_pg_blobtable,
                   HttpVerdictStream, postgres, qhttpjudge, 'http_verdict'+bckt, 'http_verdict'),
        )
        queues = (qreport, qmsm, qtcp, qdns, qhttpctrl, qhttpreq, qhttpjudge)

        c.execute('SELECT filename, frame_off, frame_size, intra_off, intra_size, report_no, msm_no '
                  'FROM autoclaved_meta{} JOIN report_meta{} USING (autoclaved_no) JOIN measurement_meta{} USING (report_no) '
                  'ORDER BY filename, frame_off, intra_off'.format(bckt, bckt, bckt))
        for filename, itfile in groupby(c, itemgetter(0)):
            with open(os.path.join(in_root, filename)) as fd:
                for (frame_off, frame_size), itframe in groupby(itfile, itemgetter(1, 2)):
                    assert fd.tell() == frame_off
                    blob = fd.read(frame_size)
                    assert len(blob) == frame_size
                    blob = lz4frame.decompress(blob)
                    for filename, frame_off, frame_size, intra_off, intra_size, report_no, msm_no in itframe:
                        datum = blob[intra_off:intra_off+intra_size]
                        assert len(datum) == intra_size
                        datum = ujson.loads(datum)
                        for q in queues:
                            q.put((report_no, msm_no, datum))
        for q in queues:
            q.close()
        for f in futures:
            f.get()
        c.execute('INSERT INTO autoclaved SELECT * FROM autoclaved_meta{}'.format(bckt))
        c.execute('INSERT INTO report '
            'SELECT report_no, autoclaved_no, test_start_time, probe_cc, probe_asn, probe_ip, '
                    'test_name, badtail, textname, orig_sha1, '
                    '''COALESCE(report_id, translate(encode(orig_sha1, 'base64'), '/+=', '_-')), software_no '''
            'FROM report_meta{bckt} JOIN report_blob{bckt} USING (report_no)'.format(bckt=bckt))
        c.execute('INSERT INTO measurement '
            'SELECT msm_no, report_no, frame_off, frame_size, intra_off, intra_size, '
                    'measurement_start_time, test_runtime, orig_sha1, id, input_no '
            'FROM measurement_meta{bckt} JOIN measurement_blob{bckt} USING(msm_no)'.format(bckt=bckt))
        for t in ('tcp', 'dns_a', 'http_control', 'http_request', 'http_verdict'):
            c.execute('INSERT INTO {t} SELECT * FROM {t}{bckt}'.format(t=t, bckt=bckt))
        tables = ('autoclaved_meta', 'report_meta', 'measurement_meta', 'report_blob', 'measurement_blob',
                  'tcp', 'dns_a', 'http_control', 'http_request', 'http_verdict')
        for t in tables:
            c.execute('DROP TABLE {}{}'.format(t, bckt))

########################################################################

def parse_args():
    p = argparse.ArgumentParser(description='ooni-pipeline: public/autoclaved -> *')
    p.add_argument('--start', metavar='ISOTIME', type=isomidnight, help='Airflow execution date', required=True)
    p.add_argument('--end', metavar='ISOTIME', type=isomidnight, help='Airflow execution date + schedule interval', required=True)
    p.add_argument('--autoclaved-root', metavar='DIR', type=dirname, help='Path to .../public/autoclaved', required=True)
    p.add_argument('--mode', choices=('simhash-text', 'meta-pg'), required=True)

    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument('--simhash-root', metavar='DIR', type=dirname, help='Path to .../public/simhash')
    dest.add_argument('--postgres', metavar='DSN', help='libpq data source name')

    opt = p.parse_args()
    if (opt.end - opt.start) != timedelta(days=1):
        p.error('The script processes 24h batches')
    if opt.mode == 'simhash-text' and opt.simhash_root is None:
        p.error('`--mode simhash-text` requires `--simhash-root`')
    if opt.mode == 'meta-pg' and opt.postgres is None:
        p.error('`--mode meta-pg` requires `--postgres`')
    return opt

def main():
    opt = parse_args()
    bucket = opt.start.strftime('%Y-%m-%d')
    if opt.mode == 'simhash-text':
        simhash_text(opt.autoclaved_root, opt.simhash_root, bucket)
    elif opt.mode == 'meta-pg':
        meta_pg(opt.autoclaved_root, bucket, opt.postgres)

if __name__ == '__main__':
    main()
