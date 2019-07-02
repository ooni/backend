#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import gzip
import os
import shutil
import tempfile
from contextlib import closing, contextmanager


@contextmanager
def ScopedTmpdir(*args, **kwargs):
    tmpdir = tempfile.mkdtemp(*args, **kwargs)
    try:
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir)


@contextmanager
def open_tmp_gz(fullpath, mode="wb", chmod=None):
    if os.path.exists(fullpath):  # this check is for convenience, to fail early
        raise RuntimeError("File already exists", fullpath)
    out_dir = os.path.dirname(fullpath)
    filename = os.path.basename(fullpath)
    if filename.endswith(".gz"):
        filename = filename[:-3]
    with tempfile.NamedTemporaryFile(prefix="tmpoopl", dir=out_dir) as fdraw:
        with closing(
            gzip.GzipFile(filename=filename, mode=mode, fileobj=fdraw)
        ) as fdgz:
            yield fdgz
        fdraw.flush()
        # no exception happened, gzip stream is closed and flushed now
        os.link(fdraw.name, fullpath)  # link() instead of rename() to avoid overwrite
    if chmod is not None:
        os.chmod(fullpath, chmod)


@contextmanager
def open_tmp(fullpath, mode="wb", chmod=None):
    if os.path.exists(fullpath):  # this check is for convenience, to fail early
        raise RuntimeError("File already exists", fullpath)
    out_dir = os.path.dirname(fullpath)
    with tempfile.NamedTemporaryFile(prefix="tmpoopl", dir=out_dir) as fdraw:
        yield fdraw
        fdraw.flush()
        # no exception happened
        os.link(fdraw.name, fullpath)  # link() instead of rename() to avoid overwrite
    if chmod is not None:
        os.chmod(fullpath, chmod)
