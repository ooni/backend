#!/usr/bin/env python2

# That's a sanity check to ensure that we can migrate from historical public/sanitised to public/autoclaved:
# 1. every sanitised/ file is in autoclaved/
# 2. every sanitised/ file almost equals corresponding autoclaved/
# 3. DOES NOT check that every autoclaved/ is in sanitised/ (that's not true as some reports-raw were never sanitised)
#
# This sanity check means that sanitised/ is safe to delete.

import argparse
import datetime
import hashlib
import os
import tempfile
from functools import partial

import ujson

import autoclaving
from canning import dirname
from centrifugation import stream_datum, FILE_START, FILE_END, REPORT_START, REPORT_END, BADBLOB, DATUM

def parse_time(s):
    return datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S')

def calc_santoken(sanitised_root, autoclaved_root, bucket):
    known_sanitised = sorted('{}/{}'.format(bucket, _) for _ in os.listdir(os.path.join(sanitised_root, bucket)))
    santoken = hashlib.sha1()
    with open(os.path.join(autoclaved_root, bucket, autoclaving.INDEX_FNAME), 'rb') as fd:
        for blob in iter(partial(fd.read, 1048576), ''):
            santoken.update(blob)
    santoken.update('\0'.join(known_sanitised))
    return santoken.hexdigest()

def check_sanitised(autoclaved_root, sanitised_root, bucket):
    san_obj, auto_obj = object(), object()
    # FIXME: it's technicaly a race condition :)
    santoken = calc_santoken(sanitised_root, autoclaved_root, bucket)
    known_sanitised = set('{}/{}'.format(bucket, _) for _ in os.listdir(os.path.join(sanitised_root, bucket)))
    datum_iter = stream_datum(autoclaved_root, bucket)
    for ev, doc in datum_iter:
        assert ev is FILE_START
        for ev, doc in datum_iter:
            if ev is FILE_END:
                break
            assert ev is REPORT_START
            textname = doc['textname']
            if textname.endswith('.yaml'):
                textname = textname[:-5] + '.json'
            sanpath = os.path.join(sanitised_root, textname)
            if os.path.exists(sanpath):
                saniter = autoclaving.stream_json_blobs(open(sanpath))
                for ev, doc in datum_iter:
                    if ev is DATUM:
                        san = ujson.loads(next(saniter)[1])
                        auto = doc['datum']

                        del san['id'], auto['id'] # it was random

                        # wrong TZ during sanitisation, autoclaved enforces UTC
                        if san['test_start_time'] != auto['test_start_time']:
                            if san['test_start_time'].startswith('1970-01-01 '): # something like 1970-01-01 01:00:00
                                del san['test_start_time'], auto['test_start_time']
                            else:
                                dt = parse_time(san['test_start_time']) - parse_time(auto['test_start_time'])
                                if dt.days == 0 and (dt.seconds % 3600) == 0: # something like 2016-12-31 07:26:22 vs. 2016-12-31 06:26:22
                                    del san['test_start_time'], auto['test_start_time']
                            # `report_id` may use test_start_time as prefix: 20161231T072622Z_MhNAwTSRMIyWmzudgbdteCPUNUpzaShRsfBvCfzLePvbeHGcWF
                            if 'Z_' in san['report_id']:
                                san['report_id'] = san['report_id'].split('Z_', 1)[1]
                                auto['report_id'] = auto['report_id'].split('Z_', 1)[1]
                        if san['measurement_start_time'] != auto['measurement_start_time']: # another wrong TZ
                            dt = parse_time(san['measurement_start_time']) - parse_time(auto['measurement_start_time'])
                            if dt.days == 0 and (dt.seconds % 3600) == 0:
                                del san['measurement_start_time'], auto['measurement_start_time'] # something like 2016-12-31 07:26:34 vs 2016-12-31 06:26:34

                        # `autoclaved` preserves `.yaml` extention is `report_filename`, `sanitised` replaces with `.json`
                        if san['report_filename'] != auto['report_filename'] and auto['report_filename'][-5:] == '.yaml':
                            auto['report_filename'] = auto['report_filename'][:-5] + '.json'

                        # that's some useless(?) empty list in `sanitised`
                        for k in ('sent', 'received'):
                            if k in san and k not in auto and san[k] == []:
                                del san[k]

                        for k in san.keys():
                            if san.get(k, san_obj) == auto.get(k, auto_obj):
                                del san[k], auto[k]
                        if san != doc['datum']:
                            raise RuntimeError(textname, 'mismatch', san, doc['datum'])

                    elif ev is BADBLOB:
                        pass
                    elif ev is REPORT_END:
                        if next(saniter, None) is not None:
                            raise RuntimeError(textname, 'leftover in sanitised')
                        known_sanitised.remove(textname)
                        break
                    else:
                        raise RuntimeError('Unexpected event type', doc['type'])
            else: # okay, no corresponding sanitised file
                for ev, _ in datum_iter:
                    # wasting cycles in reading and decompression
                    if ev is REPORT_END:
                        break
                    elif ev not in (DATUM, BADBLOB):
                        raise RuntimeError('Unexpected event type', doc['type'])
            assert ev is REPORT_END
        assert ev is FILE_END
    if known_sanitised:
        raise RuntimeError('Some sanitised files are not autoclaved', known_sanitised)
    return santoken

def parse_args():
    p = argparse.ArgumentParser(description='ooni-pipeline: verify that public/autoclaved contains public/sanitised')
    p.add_argument('--bucket', metavar='BUCKET', help='Bucket to check', required=True)
    p.add_argument('--sanitised-root', metavar='DIR', type=dirname, help='Path to .../public/sanitised', required=True)
    p.add_argument('--autoclaved-root', metavar='DIR', type=dirname, help='Path to .../public/autoclaved', required=True)
    p.add_argument('--santoken', metavar='FILE', help='Token for checked sanitised directory', required=True)
    opt = p.parse_args()
    # that's not `os.path.join` to verify _textual_ value of the option
    dirname('{}/{}'.format(opt.sanitised_root, opt.bucket))
    dirname('{}/{}'.format(opt.autoclaved_root, opt.bucket))
    return opt

def main():
    opt = parse_args()

    if os.path.exists(opt.santoken):
        with open(opt.santoken) as fd:
            stored_santoken = fd.read()
        santoken = calc_santoken(opt.sanitised_root, opt.autoclaved_root, opt.bucket)
        if stored_santoken == santoken:
            print 'santoken is up to date'
            return
        else:
            raise RuntimeError('Stale santoken exists', opt.santoken, stored_santoken, santoken)

    with tempfile.NamedTemporaryFile(prefix='tmpst', dir=os.path.dirname(opt.santoken)) as fd:
        santoken = check_sanitised(opt.autoclaved_root, opt.sanitised_root, opt.bucket)
        fd.write(santoken)
        fd.flush()
        os.link(fd.name, opt.santoken)
    os.chmod(opt.santoken, 0444)

if __name__ == '__main__':
    main()
