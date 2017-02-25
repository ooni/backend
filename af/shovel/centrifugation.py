#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import argparse
import base64
import gzip
import itertools
import os
import re
import tempfile
from datetime import timedelta
from contextlib import closing

import lz4.frame as lz4frame
import mmh3
import simhash
import ujson

import autoclaving
from canning import isomidnight, dirname

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
                pass # FIXME: must be processed for `release`

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
        body = base64.b64decode(body['data'])
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

def parse_args():
    p = argparse.ArgumentParser(description='ooni-pipeline: public/autoclaved -> *')
    p.add_argument('--start', metavar='ISOTIME', type=isomidnight, help='Airflow execution date', required=True)
    p.add_argument('--end', metavar='ISOTIME', type=isomidnight, help='Airflow execution date + schedule interval', required=True)
    p.add_argument('--autoclaved-root', metavar='DIR', type=dirname, help='Path to .../public/autoclaved', required=True)
    p.add_argument('--mode', choices=('simhash-text',), required=True)
    p.add_argument('--simhash-root', metavar='DIR', type=dirname, help='Path to .../public/simhash')
    opt = p.parse_args()
    if (opt.end - opt.start) != timedelta(days=1):
        p.error('The script processes 24h batches')
    if opt.mode == 'simhash-text' and opt.simhash_root is None:
        p.error('`--mode simhash-text` requires `--simhash-root`')
    return opt

def main():
    opt = parse_args()
    bucket = opt.start.strftime('%Y-%m-%d')
    simhash_text(opt.autoclaved_root, opt.simhash_root, bucket)

if __name__ == '__main__':
    main()
