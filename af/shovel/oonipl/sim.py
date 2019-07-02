#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import itertools
import re

import mmh3
import simhash

WORD_RE = re.compile(
    """[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f !"#$%&\'()*+,-./:;<=>?@[\\\\\\]^_`{|}~']+"""
)
NONTEXT_RE = re.compile(
    """[\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f !"#$%&\'()*+,-./:;<=>?@[\\\\\\]^_`{|}~']+"""
)
SPACE_RE = re.compile(
    "[\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f ]+"
)

# 1. HTML comment may contain anything
# 2. javascript may contain style in a string
# 3. css is probably not that mad
# 4. tags are not that important
# So the order to strip them is outlined abouve :-)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.IGNORECASE | re.DOTALL)
SCRIPT_RE = re.compile(
    r"<\s*script\s*[^>]*>.*?</\s*script\s*>", re.IGNORECASE | re.DOTALL
)
STYLE_RE = re.compile(r"<\s*style\s*[^>]*>.*?</\s*style\s*>", re.IGNORECASE | re.DOTALL)
HTML_ENTITIES_RE = re.compile(r"&#?[xX]?(?:[0-9a-fA-F]+|\w{1,8})[;\s]")
HTML_TAGS_RE = re.compile(r"<.*?>", re.IGNORECASE | re.DOTALL)

# NB: It makes little sense to use both 64bit numbers from MurmurHash3 to compare
# hashes as pairwise Hamming distance using high 64bit is highly correlated
# with the distance computed using low 64bit. It's actually expected, but
# it means, that summing these distances is not linear and should be avoided.
# -- https://gist.github.com/darkk/e2b2762c4fe053a3cf8a299520f0490e

# mmh3.hash64 produces pairs of signed i64
# simhash.compute expects list of unsigned ui64 and produces unsigned ui64
# postgres has signed i64, so it's converted back


def sim_shi4_mm3_layout(text):
    text = SPACE_RE.sub(" ", text)  # replace all runs of spaces

    i1, i2 = itertools.tee(WORD_RE.finditer(text))
    for _ in xrange(3):  # 4 words per shingle
        next(i2, None)

    hash64 = mmh3.hash64
    # NB: `array` of i64 & ui64 is Python 3.3+
    mm = [
        hash64(text[m1.start() : m2.end()])[0] & 0xFFFFFFFFFFFFFFFF
        for m1, m2 in itertools.izip(i1, i2)
    ]
    r = simhash.compute(mm)
    return r - 0x10000000000000000 if r > 0x7FFFFFFFFFFFFFFF else r


def sim_shi4_mm3_text(text):
    text = HTML_COMMENT_RE.sub(" ", text)
    text = SCRIPT_RE.sub(" ", text)
    text = STYLE_RE.sub(" ", text)
    text = HTML_TAGS_RE.sub(" ", text)
    text = HTML_ENTITIES_RE.sub(" ", text)
    text = NONTEXT_RE.sub(" ", text)  # replace all runs of spaces and punctuation

    i1, i2 = itertools.tee(WORD_RE.finditer(text))
    for _ in xrange(3):  # 4 words per shingle
        next(i2, None)

    hash64 = mmh3.hash64
    # NB: `array` of i64 & ui64 is Python 3.3+
    mm = [
        hash64(text[m1.start() : m2.end()])[0] & 0xFFFFFFFFFFFFFFFF
        for m1, m2 in itertools.izip(i1, i2)
    ]
    r = simhash.compute(mm)
    return r - 0x10000000000000000 if r > 0x7FFFFFFFFFFFFFFF else r
