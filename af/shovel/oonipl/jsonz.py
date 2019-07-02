#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
# It's not named `json.py` to avoid obvious conflict with `json` module.

import json
import gzip


def json_gz(fname):
    return json.load(gzip.GzipFile(fname))


def jsonl_gz(fname):
    return map(json.loads, gzip.GzipFile(fname))
