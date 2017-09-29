#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import argparse
import gzip
import json
import os

from canning import dirname, load_verified_index, listdir_filesize

def s3_ls_jsongz(fname):
    return json.load(gzip.GzipFile(fname))

def cleanup_reports_raw(reports_raw_root, canned_root, bucket, s3_ls):
    if 'private/reports-raw/' not in s3_ls['metadata']['url']:
        raise RuntimeError('Unexpected s3.metadata.url', s3_ls['metadata'])
    s3_size = {'/'.join(_['file_name'].rsplit('/', 2)[-2:]): _['file_size'] for _ in s3_ls['results']}

    canned_size = {}
    for caninfo in load_verified_index(os.path.join(canned_root, bucket), bucket):
        if 'canned' in caninfo:
            canned_size.update((_['textname'], _['text_size']) for _ in caninfo['canned'])
        else:
            canned_size[caninfo['textname']] = caninfo['text_size']

    for fname, size in listdir_filesize(os.path.join(reports_raw_root, bucket)):
        idfname = '{}/{}'.format(bucket, fname)
        if size > 0 and s3_size.get(idfname) == canned_size.get(idfname) == size:
            os.unlink(os.path.join(reports_raw_root, bucket, fname))
        elif idfname in s3_size or idfname in canned_size:
            print idfname, 'FS:', size, 'S3:', s3_size.get(idfname), 'canned:', canned_size.get(idfname)

def parse_args():
    p = argparse.ArgumentParser(description='ooni-pipeline: remove files from private/reports-raw that are stored in private/canned and s3')
    p.add_argument('--bucket', metavar='BUCKET', help='Bucket to check', required=True)
    p.add_argument('--reports-raw-root', metavar='DIR', type=dirname, help='Path to .../private/reports-raw', required=True)
    p.add_argument('--canned-root', metavar='DIR', type=dirname, help='Path to .../private/canned', required=True)
    p.add_argument('--s3-ls', metavar='S3_LS', type=s3_ls_jsongz, help='Path to s3-ls.json.gz output of aws_s3_ls.py', required=True)
    opt = p.parse_args()
    # that's not `os.path.join` to verify _textual_ value of the option
    dirname('{}/{}'.format(opt.reports_raw_root, opt.bucket))
    dirname('{}/{}'.format(opt.canned_root, opt.bucket))
    return opt

def main():
    opt = parse_args()
    cleanup_reports_raw(opt.reports_raw_root, opt.canned_root, opt.bucket, opt.s3_ls)

if __name__ == '__main__':
    main()
