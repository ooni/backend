#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import gzip
import json
import tempfile
import contextlib


class NotACannedIndexRow(RuntimeError):
    pass


# There may be other keys, but these must be present.
# See `canning.py` for more.
CANNED_ROW_KEYS = {"file_sha1", "file_crc32", "file_size", "filename"}


def load_index(fileobj):
    index = []
    with gzip.GzipFile(fileobj=fileobj, mode="r") as fd:
        for line in fd:
            if line[-1] != "\n":
                raise CannerError("Bad line end")
            row = json.loads(line[:-1])  # json doesn't grok memoryview
            if len(row.viewkeys() & CANNED_ROW_KEYS) != len(CANNED_ROW_KEYS):
                raise NotACannedIndexRow(row)
            index.append(row)
    return index


@contextlib.contextmanager
def flistz_tempfile(files, bucket=None):
    # Create list of NUL-terminated files suitable for tar `--files-from`.
    with tempfile.NamedTemporaryFile(prefix="flistz") as flistz:
        for name in files:
            if bucket is not None:
                s = bucket + "/" + name + "\0"
            else:
                s = name + "\0"
            flistz.write(s)
        flistz.flush()
        yield flistz.name
