#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import shutil
import tempfile
from contextlib import contextmanager

@contextmanager
def ScopedTmpdir(*args, **kwargs):
    tmpdir = tempfile.mkdtemp(*args, **kwargs)
    try:
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir)
