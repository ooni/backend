#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import os
import datetime


def filename(s):
    if not os.path.isfile(s):
        raise ValueError("Not a file", s)
    return s


def dirname(s):
    if not os.path.isdir(s):
        raise ValueError("Not a directory", s)
    if s[-1] == "/":
        raise ValueError("Bogus trailing slash", s)
    return s


def isodatetime(s):
    # Reverse of `datetime.isoformat()` besides microseconds & timezones
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")


def isomidnight(s):
    s = isodatetime(s)
    if s.hour == s.minute == s.second == s.microsecond == 0:
        return s
    raise ValueError("isodatetime is not midnight-aligned", s)
