#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

from subprocess import Popen, PIPE
from contextlib import contextmanager


@contextmanager
def ScopedPopen(*args, **kwargs):
    proc = Popen(*args, **kwargs)
    try:
        yield proc
    finally:
        try:
            proc.kill()
        except Exception:
            pass
