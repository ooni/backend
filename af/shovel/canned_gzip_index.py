#!/usr/bin/env python2
"""
This was a one-off script used to create a compressed version of index files.

It should probably be dropped as it's not referred to outside of the Dockerfile.
"""

import gzip
import os
import sys
import tempfile
from contextlib import closing


def gzip_canning_index(fname):
    basename = os.path.basename(fname)
    mtime = os.path.getmtime(fname)
    outdir = os.path.abspath(os.path.dirname(fname))
    with open(fname) as textin, tempfile.NamedTemporaryFile(
        prefix="tmpcng", dir=outdir
    ) as rawout:
        with closing(
            gzip.GzipFile(filename=basename, mtime=mtime, mode="wb", fileobj=rawout)
        ) as textout:
            for line in textin:
                if line[:1] == "{" and line[-2:] == "}\n":
                    textout.write(line)
                elif line == "\n":
                    if next(textin, None) is None:
                        # NB: explicit EOF is not stored, gzip has CRC32 and
                        # file length, python module gzip checks them
                        break
                    else:
                        raise RuntimeError("Data after explicit EOF")
                else:
                    raise RuntimeError("Bad line format", line)
            else:
                raise RuntimeError("No explicit EOF")
        os.link(rawout.name, fname + ".gz")
    os.chmod(fname + ".gz", 0444)


def main():
    for fname in sys.argv[1:]:
        gzip_canning_index(fname)


if __name__ == "__main__":
    main()
