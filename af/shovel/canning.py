#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import argparse
import datetime
import gzip
import json
import operator
import os
import re
import stat
import sys
import tarfile
import tempfile
import threading
import time
import traceback
from base64 import b64encode
from contextlib import closing
from hashlib import sha1
from zlib import crc32  # btw, binascii.crc32 is four times slower than zlib.crc32

from oonipl.cli import dirname, isomidnight
from oonipl.popen import ScopedPopen, PIPE
from oonipl.can import load_index, flistz_tempfile
from oonipl.const import LZ4_LEVEL


class CannerError(RuntimeError):
    pass


class Future(object):
    # These poor-man futures have quite basic cleanup routines => there may be
    # no EPIPE propagation => the program may deadlock in case of error.
    # That's OK for batch tasks managed by the scheduler.
    def __init__(self, cleanup, fn, *args, **kwargs):
        self.thread = threading.Thread(
            name="%s/%x" % (fn.__name__, id(self)),
            target=self.__threaded,
            args=args,
            kwargs=kwargs,
        )
        if callable(cleanup):
            cleanup = (cleanup,)
        assert all([callable(cb) for cb in cleanup])
        self.cleanup = cleanup
        self.fn = fn
        self.retval = (
            None
        )  # raw attribute should be good enough as it's read only after `join()`
        self.exc_info = None
        self.thread.start()

    def __threaded(self, *args, **kwargs):
        try:
            self.retval = self.fn(*args, **kwargs)
        except Exception:
            self.exc_info = sys.exc_info()
            print >> sys.stderr, "Exception in the Future, something may deadlock -- ",
            traceback.print_exc(file=sys.stderr)
            for cb in self.cleanup:
                try:
                    cb()
                except Exception:
                    pass

    def get(self):
        self.thread.join()
        if self.exc_info is not None:
            raise self.exc_info[0], self.exc_info[1], self.exc_info[
                2
            ]  # type, value, traceback
        else:
            return self.retval


class NopTeeFd(object):
    @staticmethod
    def write(buf):
        pass


# Don't forget to `copy.flush()` before closing `copy` fd
class CountingTee(object):
    def __init__(self, src, copy):
        self.__src = src
        self.__copy = copy
        self.__size = 0

    def read(self, *args):
        ret = self.__src.read(*args)
        self.__size += len(ret)
        self.__copy.write(ret)
        return ret

    def tell(self):
        return self.__src.tell()

    def seek(self, dest):  # NB: no `whence` ~ whence=os.SEEK_SET
        skipwant = dest - self.tell()
        if skipwant < 0:
            raise RuntimeError("Unable to seek backwards while reading the stream")
        elif skipwant > 0:
            while skipwant:
                step = min(skipwant, 262144)
                skiplen = len(self.read(step))
                if skiplen != step:
                    raise RuntimeError("Unexpected end of file", step, skiplen)
                skipwant -= step

    @property
    def size(self):
        return self.__size


class ChecksummingTee(CountingTee):
    def __init__(self, src, copy):
        super(ChecksummingTee, self).__init__(src, copy)
        self.__crc32 = 0
        self.__sha1 = sha1()

    def read(self, *args):
        ret = super(ChecksummingTee, self).read(*args)
        self.__crc32 = crc32(ret, self.__crc32)
        self.__sha1.update(ret)
        return ret

    @property
    def crc32(self):
        assert self.__crc32 <= 0x7FFFFFFF  # it's intentionally signed!
        return self.__crc32

    @property
    def sha1(self):
        return self.__sha1.digest()


def stream_canning(fd, teefd=NopTeeFd):
    fd = ChecksummingTee(fd, teefd)
    while True:
        blob = fd.read(1048576)
        if not blob:
            break
    return {
        "text_crc32": fd.crc32,
        "text_size": fd.size,
        "text_sha1": b64encode(fd.sha1),
    }


def tarfile_canning(fileobj):
    """
    Given open tar file as a `fileobj` this function enumerates measurements
    stored in the tar file, calculates various checksums and produces alike
    list for further processing:

    [{'textname': 'sample/20160928T062804Z-GR-AS6799-http_header_field_manipulation-20160928T062523Z_AS6799_5uajV5x6HsOQIgJJXEjBOuiwl2IqQrwQqTzvHO2oPcQ4RLo1nB-0.2.0-probe.json',
      'text_crc32': -389142680,
      'text_sha1': 'dpp4Xw07a7wxyNC4ZrLsUOTwmL8=',
      'text_size': 2380},
     {'textname': 'sample/20160928T115926Z-CA-AS5645-http_requests-FZWzSKY0mmtnpZtd9ztY7qQULTI3Fisi19jC0XoDuBwsiJN9N4QUpLlNR45jvePB-0.1.0-probe.yaml',
      'text_crc32': 215745312,
      'text_sha1': 'oqm9kQzhQKT8+PPrLLjqAl4PfhU=',
      'text_size': 363559}]
    """
    canned = []
    with tarfile.open(mode="r|", fileobj=fileobj) as tarfd:
        for tin in tarfd:
            if not tin.isfile():
                raise CannerError("Non-regular file in the tar", tin.name, tin.type)
            with closing(tarfd.extractfile(tin)) as fd:
                can = stream_canning(fd)
                if (
                    tin.size != can["text_size"]
                ):  # safety net, `tarfile` detects the case itself
                    raise CannerError("Bad tar file size", tin.size, can["text_size"])
                can["textname"] = tin.name
                canned.append(can)
    return canned


def raw_canning_feeder(raw_in, raw_out):
    # Reads reports-raw from `raw_in`, copies it to `raw_out`,
    # calculates measurements-aware digest on the fly.
    can = stream_canning(raw_in, raw_out)
    raw_out.flush()
    return can


def tarfile_canning_feeder(tar_in, tar_out):
    # Reads tarfile full of reports-raw files from `tar_in`, copies it to
    # `tar_out` and calculates measurements-aware digest on the fly.
    tee = CountingTee(tar_in, tar_out)
    can = tarfile_canning(tee)
    tar_out.flush()
    return {"canned": can, "text_size": tee.size}


def blob_checksumming_feeder(blob_in, blob_out):
    # Reads something from `blob_in`, copies it to `blob_out`, calculates
    # ordinary blob digest on the fly.
    can = stream_canning(blob_in, blob_out)
    blob_out.flush()
    return {
        "file_crc32": can["text_crc32"],
        "file_size": can["text_size"],
        "file_sha1": can["text_sha1"],
    }


REPORT_FNAME_RE = re.compile(
    r"^\d{4}[0-1][0-9][0-3][0-9]T[0-2][0-9][0-5][0-9][0-5][0-9]Z-[A-Z]{2}-AS\d+-(?P<test_name>[^-]+)-[^-]+-[.0-9]+-probe\.(?:yaml|json)$"
)


def pack_bucket(listing, can_size=64 * 1048576):
    # Distribution of OONI reports file size is trimodal: LOTS of small files
    # less than <1Mbyte, some files having size like ~20±5 Mbytes and some more
    # files in 97±20 Mbytes range. 64 Mbytes cutoff is chosen to split the
    # third group into separate one that is compressed without tar overhead.
    # Storage of mtime & other attributes is not the main objective.
    #
    # The code produces reproducible ordering, so it may also produce some
    # stupid outputs like [2 Mb tarfile, 63 Mb tarfile, 2 Mb tarfile] in
    # pathological cases.
    tar = {}
    asis = []
    for pair in listing:
        fname, size = pair
        m = REPORT_FNAME_RE.match(fname)
        if m is None:
            raise CannerError("Unable to parse report filename", fname)
        if size < can_size:
            tar.setdefault(m.group("test_name"), []).append(pair)
        else:
            asis.append(fname)

    tarfiles = {}
    for test_name in tar:
        tar[test_name].sort(key=operator.itemgetter(0))

        slices = {}
        slice_no, slice_size = 0, 0
        slices[slice_no] = dest = []

        for fname, size in tar[test_name]:
            if slice_size + size >= can_size:
                # the next file goes to the next slice, but single-file slices
                # are stupid, so they are stored as-is
                if len(dest) == 1:
                    asis.extend(dest)
                    del slices[slice_no]
                    slice_no -= 1
                slice_no += 1
                slice_size = 0
                slices[slice_no] = dest = []
            dest.append(fname)
            slice_size += size
        if len(dest) == 1:
            asis.extend(dest)
            del slices[slice_no]
            slice_no -= 1
        # Undersized last chunk is not appended to the previous one as
        # pathological cases for small files are still possible due to
        # reproducible ordering and the last chunk is not that special.

        digits = str(len(str(slice_no)))
        slice_fmt = "%s.%0" + digits + "d.tar"
        for slice_no, dest in slices.iteritems():
            tarfiles[slice_fmt % (test_name, slice_no)] = dest

    return asis, tarfiles


def can_to_tar(input_root, bucket, slice_files, output_dir, fname):
    # Size of argv array is limited, `getconf ARG_MAX` shows ~2 Mbytes on
    # modern Linux, but it may vary across platforms & devices with different
    # memory size. The code for pipeline-16.10 uses up to ~170 Kbytes of the
    # limit while grouping files at 64 Mbytes boundary with pack_bucket().
    # But one year later `ndt` arrived with lots of small measuements (4KiB per
    # report) and it leads to 8MiB CLI arg. That's why `--add-file` is not used
    # anymore. `--verbatim-files-from` option is not available for `tar` from
    # Ubuntu-16.04, so it's not used as well.
    with tempfile.NamedTemporaryFile(prefix="tmpcan", dir=output_dir) as fdout, open(
        os.devnull, "rb"
    ) as devnull, flistz_tempfile(
        slice_files, bucket=bucket
    ) as files_from, ScopedPopen(
        [
            "tar",
            "--create",
            "--directory",
            input_root,
            "--null",
            "--files-from",
            files_from,
        ],
        stdin=devnull,
        stdout=PIPE,
    ) as proc_tar, ScopedPopen(
        ["lz4", LZ4_LEVEL], stdin=PIPE, stdout=PIPE
    ) as proc_lz4:

        cleanup = (proc_tar.kill, proc_lz4.kill)  # circuit breaker
        can = Future(cleanup, tarfile_canning_feeder, proc_tar.stdout, proc_lz4.stdin)
        chksum = Future(cleanup, blob_checksumming_feeder, proc_lz4.stdout, fdout)

        can = can.get()
        proc_tar.wait()
        if proc_tar.returncode != 0:
            raise CannerError(
                "tar failed with non-zero returncode", proc_tar.returncode
            )
        proc_lz4.stdin.close()  # signal EOF

        chksum = chksum.get()
        proc_lz4.wait()
        if proc_lz4.returncode != 0:
            raise CannerError(
                "lz4 failed with non-zero returncode", proc_lz4.returncode
            )

        assert not (can.viewkeys() & chksum.viewkeys())
        can.update(chksum)
        can["filename"] = os.path.join(bucket, fname + ".lz4")
        output_file = os.path.join(output_dir, fname + ".lz4")
        os.link(
            fdout.name, output_file
        )  # 1. `link` does not overwrite dest, 2. temp name is auto-cleaned
    return output_file, can


def can_to_blob(input_fname, bucket, output_dir, fname):
    with open(input_fname, "rb") as fdin, tempfile.NamedTemporaryFile(
        prefix="tmpcan", dir=output_dir
    ) as fdout, ScopedPopen(["lz4", LZ4_LEVEL], stdin=PIPE, stdout=PIPE) as proc_lz4:

        can = Future(proc_lz4.kill, raw_canning_feeder, fdin, proc_lz4.stdin)
        chksum = Future(proc_lz4.kill, blob_checksumming_feeder, proc_lz4.stdout, fdout)

        can = can.get()
        proc_lz4.stdin.close()

        chksum = chksum.get()
        proc_lz4.wait()
        if proc_lz4.returncode != 0:
            raise CannerError(
                "lz4 failed with non-zero returncode", proc_lz4.returncode
            )

        assert not (can.viewkeys() & chksum.viewkeys())
        can["textname"] = os.path.join(bucket, fname)
        can["filename"] = os.path.join(bucket, fname + ".lz4")
        can.update(chksum)
        output_file = os.path.join(output_dir, fname + ".lz4")
        os.link(fdout.name, output_file)
    return output_file, can


# Not to be confused with `manifest.json`.
INDEX_FNAME = "index.json.gz"
EPOCH = int(time.time())  # time to be stamped in produced tar files


def finalize_can(output_file, can, fdindex):
    output_size = os.stat(output_file).st_size  # all the files closed, buffers flushed
    if output_size != can["file_size"]:  # e.g. due to low disk space & buffering
        raise CannerError("File size", output_file, output_size, can["file_size"])
    os.chmod(output_file, 0444)  # to o+r and prevent accidental modification
    json.dump(can, fdindex, sort_keys=True)
    fdindex.write("\n")


def listdir_filesize(d):
    filesize = []
    for fname in os.listdir(d):
        st = os.stat(os.path.join(d, fname))
        if stat.S_ISREG(st.st_mode):
            filesize.append((fname, st.st_size))
    return filesize


def load_verified_index(output_dir, bucket):
    """
    - Every file from `output_dir` exists in index
    - Nothing but `output_dir` exists in index
    - Declared file_size matches length of actual files
    """
    index_fpath = os.path.join(output_dir, INDEX_FNAME)
    with open(index_fpath) as fd:
        index = load_index(fd)
    ndxsize = {_["filename"]: _["file_size"] for _ in index}
    outsize = {
        os.path.join(bucket, f): sz
        for f, sz in listdir_filesize(output_dir)
        if f != INDEX_FNAME
    }
    if ndxsize != outsize:
        raise CannerError("Mismatching set of output files", output_dir)
    return index


def verify_index_input(index, bucket, filesize):
    """
    Index tracks the same set of text files under the `bucket` as `filesize`.
    """
    filesize = {"{}/{}".format(bucket, k): v for k, v in filesize}  # fname -> len
    ndxsize = {}
    for i in index:
        if "canned" in i:
            for j in i["canned"]:
                ndxsize[j["textname"]] = j["text_size"]
        else:
            ndxsize[i["textname"]] = i["text_size"]
    if filesize != ndxsize:
        raise CannerError("Mismatching set of input files", bucket)


def verify_index_ordering(index, bucket, filesize, asis, tarfiles):
    # XXX: dead code at the moment
    """
    - Everything from `input` exists in index
    - Nothing but `input` exists in index
    - Declared text_size matches length of provided files
    - Ordering & slicing is NOT verified
    """
    assert len(filesize) == len(asis) + sum(map(len, tarfiles.itervalues()))
    filesize = {"{}/{}".format(bucket, k): v for k, v in filesize}  # fname -> len

    bktasis = {k: filesize[k] for k in ("{}/{}".format(bucket, _) for _ in asis)}
    ndxasis = {_["textname"]: _["text_size"] for _ in index if "canned" not in _}
    if bktasis != ndxasis:  # NB: ordering!
        raise CannerError("Mismatching set of as-is files", bucket)

    bkttars = {"{}/{}.lz4".format(bucket, _): v for _, v in tarfiles.iteritems()}
    ndxtars = {_["filename"]: _["canned"] for _ in index if "canned" in _}
    if bkttars.viewkeys() != ndxtars.viewkeys():
        raise CannerError("Mismatching set of tar files", bucket)

    for tar in bkttars:
        if bkttars[tar] != [_["textname"] for _ in ndxtars[tar]]:  # NB: ordering!
            raise CannerError("Mismatching set of files in the tar", bucket, tar)
        for i in ndxtars[tar]:
            if filesize[i["textname"]] != i["text_size"]:
                raise CannerError("Mismatching file size", bucket, tar, i["textname"])


def canning(input_root, output_root, bucket):
    """
    The canning procedure is done daily. Objectives:
    - store raw files in compressed streaming-friendly well-known format
    - minimise incompatibility avoiding changes to the stream provided by well-known tools
    - pack tiny files into single blob to save IOPS while reading
    - store manifest to ease data scrubbing
    - read raw files exactly once to save disk bandwidth and lower pagecache pollution
    """
    assert input_root[-1] != "/" and output_root[-1] != "/" and "/" not in bucket
    input_dir = os.path.join(input_root, bucket)
    output_dir = os.path.join(output_root, bucket)
    # Bucket MUST exist as single bucket is mounted to data processing container.
    assert os.path.isdir(input_dir) and os.path.isdir(output_dir)

    filesize = listdir_filesize(input_dir)

    index_fpath = os.path.join(output_dir, INDEX_FNAME)
    if os.path.exists(index_fpath):  # verify if everything is OK or die
        index = load_verified_index(output_dir, bucket)
        verify_index_input(index, bucket, filesize)
        print "The bucket {} is already canned".format(bucket)
        return

    asis, tarfiles = pack_bucket(filesize)

    with tempfile.NamedTemporaryFile(prefix="tmpcan", dir=output_dir) as fdindex:
        with closing(
            gzip.GzipFile(
                filename="index.json", mtime=EPOCH, mode="wb", fileobj=fdindex
            )
        ) as metafd:
            for fname, slice_files in tarfiles.iteritems():
                output_file, can = can_to_tar(
                    input_root, bucket, slice_files, output_dir, fname
                )
                finalize_can(output_file, can, metafd)

            for fname in asis:
                output_file, can = can_to_blob(
                    os.path.join(input_dir, fname), bucket, output_dir, fname
                )
                finalize_can(output_file, can, metafd)

        os.link(fdindex.name, index_fpath)
    os.chmod(index_fpath, 0444)
    os.chmod(output_dir, 0555)  # done!


def parse_args():
    p = argparse.ArgumentParser(
        description="ooni-pipeline: private/reports-raw -> private/canned"
    )
    p.add_argument(
        "--start",
        metavar="ISOTIME",
        type=isomidnight,
        help="Airflow execution date",
        required=True,
    )
    p.add_argument(
        "--end",
        metavar="ISOTIME",
        type=isomidnight,
        help="Airflow execution date + schedule interval",
        required=True,
    )
    p.add_argument(
        "--reports-raw-root",
        metavar="DIR",
        type=dirname,
        help="Path to .../private/reports-raw",
        required=True,
    )
    p.add_argument(
        "--canned-root",
        metavar="DIR",
        type=dirname,
        help="Path to .../private/canned",
        required=True,
    )
    opt = p.parse_args()
    if (opt.end - opt.start) != datetime.timedelta(days=1):
        p.error("The script processes 24h batches")
    return opt


def main():
    # Default (hardcoded) lz4 compression level is benchmarked for
    # `datacollector` so the canning process is not much slower than disk write
    # speed.  TODO: write better text and/or code for quick re-benchmarking.
    #
    # Default tar can size for the bucket (64 Mbytes) is chosen due to reasons
    # described in `pack_bucket()` doc.  Tar files are merged using `test_name`
    # as the reason to reprocess the data is usually some new data mining code
    # and this code is usually test-specific.
    #
    # These are two only hardcoded values so far that may have reason to be tuned.
    opt = parse_args()
    bucket = opt.start.strftime("%Y-%m-%d")
    canning(opt.reports_raw_root, opt.canned_root, bucket)


if __name__ == "__main__":
    main()
