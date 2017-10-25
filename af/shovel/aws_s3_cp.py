#!/usr/bin/env python2

import argparse
import time
from datetime import datetime
from subprocess import check_output

if datetime.fromtimestamp(0) != datetime(1970, 1, 1, 0, 0, 0):
    raise RuntimeError('awscli requires TZ=UTC')

def parse_args():
    p = argparse.ArgumentParser(description='ooni-pipeline: AWS S3 -> copy bucket files')
    p.add_argument('--dst', metavar='DST_PATH', help='Destination path to upload files, passed to `aws s3 cp --recursive`', required=True)
    p.add_argument('--src', metavar='SRC_PATH', help='Source path to copy s3 files from, passed to `aws s3 cp --recursive``', required=True)
    opt = p.parse_args()
    return opt

def aws_s3_cp(src, dst):
    now = time.time()
    cp = check_output(['aws', 's3', 'cp', '--recursive', src, dst])
    # XXX maybe also copy a version of this that is gzip compressed
    return cp

def main():
    opt = parse_args()
    data = aws_s3_cp(opt.src, opt.dst)

if __name__ == '__main__':
    main()
