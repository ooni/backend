#!/usr/bin/env python2

import argparse
import os
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime
from subprocess import check_call

if datetime.fromtimestamp(0) != datetime(1970, 1, 1, 0, 0, 0):
    raise RuntimeError('awscli requires TZ=UTC')

def parse_args():
    p = argparse.ArgumentParser(description='ooni-pipeline: *.tar.lz4 | tar -I lz4 --extract | aws s3 sync')
    p.add_argument('--src', metavar='SRC_PATH', help='Source to decompress *.lz4 files from', required=True)
    p.add_argument('--dst', metavar='DST_PATH', help='Destination root to upload files to, passed to `aws s3 sync`', required=True)
    opt = p.parse_args()
    return opt

@contextmanager
def ScopedTmpdir(*args, **kwargs):
    tmpdir = tempfile.mkdtemp(*args, **kwargs)
    try:
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir)

def aws_s3_lz4cat_sync(src, dst):
    date = os.path.basename(src)
    for fname in os.listdir(src):
        if fname == 'index.json.gz': # FIXME: use autoclaving.INDEX_FNAME after moving it to "shared" import with constants
            continue
        # Decompressing files chunk-by-chunk saves page cache from pollution.
        # It's possible to stream files from local lz4 to S3 without touching
        # the disk and it *seems* to be easy to do that, as 80% of the volume
        # consists of "large" reports, but it makes usage of `aws s3 sync`
        # impossible, it would force me to write my own syncing code for
        # idempotent upload without wasted bandwidth and it's not something I
        # want to do right now. It may be reconsidered if we want to preserve
        # YYYY-MM-DD/xxxx naming scheme while transitioning to hourly
        # batches.  -- @darkk 2017-11-10
        with ScopedTmpdir(prefix='oolz42s3') as tmpdir: # OO lz4 to s3 :-)
            if fname.endswith('.tar.lz4'):
                # tar preserves mtime itself
                check_call(['tar', '--use-compress-program', 'lz4', '--directory', tmpdir, '--extract', '--file', os.path.join(src, fname)])
            elif fname.endswith(('.json.lz4', '.yaml.lz4')):
                os.mkdir(os.path.join(tmpdir, date))
                destname = fname[:-len('.lz4')]
                # NB: it does not preserve mtime, so `--size-only` is used.
                # Mtime may be preserved, but it's unclear if it's good idea.
                check_call(['lz4', '--decompress', os.path.join(src, fname), os.path.join(tmpdir, date, destname)])
            else:
                raise RuntimeError('Unexpected filename in the directory', src, fname)
            if os.listdir(tmpdir) != [date]: # check if bucket name is there and correct
                raise RuntimeError('Unexpected archive content, something besides usual date', date)
            check_call(['aws', 's3', 'sync', '--size-only', tmpdir, dst])

def main():
    opt = parse_args()
    aws_s3_lz4cat_sync(opt.src, opt.dst)

if __name__ == '__main__':
    main()
