#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import argparse
import os

from canning import dirname, load_verified_index, listdir_filesize


def s3_filesize(fd):
    filesize = []
    for line in fd:
        date, time, size, path = line.rstrip('\n').split(None, 4)
        size = int(size)
        if path[-1] != '/':
            filesize.append((path, size))
    return filesize

def s3_reportrs_raw(filesize):
    ret = {}
    for fname, size in filesize:
        if fname.startswith(('reports-raw/yaml/', 'reports-raw/json/')):
            fname = fname[17:] # both …/yaml/ and …/json/ have same length :)
            if fname not in ret:
                ret[fname] = size
            else:
                raise RuntimeError('Duplicate filename in `s3 ls`', fname)
    return ret

def cleanup_reports_raw(raw_root, s3, canned_root):
    for bucket in os.listdir(raw_root):
        if not os.path.exists(os.path.join(canned_root, bucket)):
            continue
        text_size = {}
        for caninfo in load_verified_index(os.path.join(canned_root, bucket), bucket):
            if 'canned' in caninfo:
                text_size.update((_['textname'], _['text_size']) for _ in caninfo['canned'])
            else:
                text_size[caninfo['textname']] = caninfo['text_size']
        for fname, size in listdir_filesize(os.path.join(raw_root, bucket)):
            idfname = '{}/{}'.format(bucket, fname)
            if size > 0 and s3.get(idfname) == text_size.get(idfname) == size:
                os.unlink(os.path.join(raw_root, bucket, fname))
            elif idfname in s3 or idfname in text_size:
                print idfname, 'FS:', size, 'S3:', s3.get(idfname), 'canned:', text_size.get(idfname)

def parse_args():
    p = argparse.ArgumentParser(description='ooni-pipeline: remove files from private/reports-raw that are stored in private/canned and listed in s3')
    p.add_argument('--reports-raw-root', metavar='DIR', type=dirname, help='Path to .../private/reports-raw', required=True)
    p.add_argument('--canned-root', metavar='DIR', type=dirname, help='Path to .../private/canned', required=True)
    p.add_argument('--s3-lslr', metavar='FILE', type=file, help='`aws s3 ls --recursive ooni-private/reports-raw/` output', required=True)
    return p.parse_args()

def main():
    opt = parse_args()
    cleanup_reports_raw(opt.reports_raw_root, s3_reportrs_raw(s3_filesize(opt.s3_lslr)), opt.canned_root)

if __name__ == '__main__':
    main()
