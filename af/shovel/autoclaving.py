#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import argparse
import functools
import gzip
import hashlib
import json
import os
import string
import tarfile
import tempfile
import time
from base64 import b64encode
from contextlib import closing
from datetime import datetime, timedelta
from hashlib import sha1
from zlib import crc32  # btw, binascii.crc32 is four times slower than zlib.crc32

import lz4.frame as lz4frame
import ujson
import yaml
from yaml import CLoader  # fail-fast if it's not built

import canning
import oonipl.can as can
import oonipl.tmp as tmp
from canning import listdir_filesize
from daily_workflow import NormaliseReport, SanitiseReport
from oonipl.cli import dirname, isomidnight
from oonipl.popen import ScopedPopen, PIPE


EPOCH = int(time.time())  # time to be stamped in produced tar files
INDEX_FNAME = "index.json.gz"
BRIDGE_DB = None  # loaded in main()


class ReadStream(object):
    def __init__(self, fileobj):
        self.__fd = fileobj
        self.__off = 0

    def tell(self):
        return self.__off

    def seek(self, dest):  # NB: no `whence`
        skipwant = dest - self.__off
        if skipwant < 0:
            raise RuntimeError("Unable to seek backwards while reading the stream")
        elif skipwant > 0:
            while skipwant:
                step = min(skipwant, 32768)
                skiplen = len(self.read(step))
                if skiplen != step:
                    raise RuntimeError("Unexpected end of file", step, skiplen)
                skipwant -= step

    def read(self, *args):
        blob = self.__fd.read(*args)
        self.__off += len(blob)
        return blob


class LZ4WriteFramedStream(object):
    def __init__(self, lz4fd, metafd, file_metadata):
        # lz4fd gets LZ4 frames
        # metafd gets metainformation about frames
        self.__text_off = 0
        self.__sha1 = sha1()
        self.__crc32 = 0
        self.__file_off = 0
        self.__file = lz4fd
        self.__meta = metafd
        self.__frame = []
        self.__frlen = 0
        json.dump(dict(type="file", **file_metadata), self.__meta, sort_keys=True)
        self.__meta.write("\n")

    def tell(self):
        return self.__text_off  # tarfile writer wants it

    def write(self, blob):
        self.write_both(blob, None)

    def write_both(self, blob, meta):
        sz = len(blob)
        if meta is not None and blob:
            meta["text_off"] = self.__text_off
            meta["text_size"] = sz
        self.__frame.append((blob, meta))
        self.__text_off += sz
        self.__frlen += sz
        self.__flush()

    def __file_write(self, blob):
        self.__file.write(blob)
        self.__file_off += len(blob)
        self.__sha1.update(blob)
        self.__crc32 = crc32(blob, self.__crc32)

    def __flush(self, force=False):
        if not force and self.__frlen < 262144:
            return
        assert sum(len(_[0]) for _ in self.__frame) == self.__frlen

        file_off = self.__file_off
        ctx = lz4frame.create_compression_context()
        self.__file_write(
            lz4frame.compress_begin(
                ctx,
                block_size=lz4frame.BLOCKSIZE_MAX4MB,  # makes no harm for larger blobs
                block_mode=lz4frame.BLOCKMODE_LINKED,
                compression_level=5,
                content_checksum=lz4frame.CONTENTCHECKSUM_ENABLED,
                # sorry, no per-block checksums yet
                auto_flush=False,
                source_size=self.__frlen,
            )
        )
        for blob, meta in self.__frame:
            self.__file_write(lz4frame.compress_update(ctx, blob))
        self.__file_write(lz4frame.compress_end(ctx))

        json.dump(
            {
                "type": "frame",
                "file_off": file_off,
                "file_size": self.__file_off - file_off,
                "text_off": self.__text_off - self.__frlen,
                "text_size": self.__frlen,
            },
            self.__meta,
            sort_keys=True,
        )
        self.__meta.write("\n")
        for blob, meta in self.__frame:
            if meta is not None:
                json.dump(meta, self.__meta, sort_keys=True)
                self.__meta.write("\n")
        json.dump({"type": "/frame"}, self.__meta)
        self.__meta.write("\n")

        self.__frame = []
        self.__frlen = 0

    def close(self):
        self.__flush(force=True)
        self.__file.flush()
        json.dump(
            {
                "type": "/file",
                "file_size": self.__file_off,
                "file_crc32": self.__crc32,
                "file_sha1": b64encode(self.__sha1.digest()),
            },
            self.__meta,
            sort_keys=True,
        )
        self.__meta.write("\n")
        self.__meta.flush()


def tarfile_write_padding(tarfd, sz):
    blocks, remainder = divmod(sz, tarfile.BLOCKSIZE)
    if remainder > 0:
        tarfd.fileobj.write("\0" * (tarfile.BLOCKSIZE - remainder))
        blocks += 1
    tarfd.offset += blocks * tarfile.BLOCKSIZE
    assert tarfd.offset == tarfd.fileobj.tell()


# Exception interrupts stream processing, tail of the stream can't be recovered.
# Single blob may be malformed, but it's out of blob parser control.


class BlobSlicerError(RuntimeError):
    pass


class BrokenFrameError(BlobSlicerError):
    pass


class TruncatedReportError(BlobSlicerError):
    pass


def stream_yaml_blobs(fd):
    head = ""
    for blob in iter(functools.partial(fd.read, 1048576), ""):
        bloboff = fd.tell() - len(blob)
        head, blob = "", head + blob
        start = 0
        while not head:
            prefix = blob[start : start + 4]
            if prefix == "---\n":  # ordinary preamble
                end = blob.find("\n...\n", start)
                if end != -1:
                    yield bloboff + start, blob[start : end + 5]
                    start = end + 5
                else:
                    head = blob[start:]
            elif not prefix:
                break
            elif prefix == "...\n":  # duplicate trailer
                # e.g. 2013-05-05/20130505T065614Z-VN-AS24173-dns_consistency-no_report_id-0.1.0-probe.yaml
                start += 4
            elif len(prefix) < 4:  # need next blob
                head = blob[start:]
            elif prefix[0] == "#":  # comment
                # e.g. 2013-09-12/20130912T144929Z-MD-AS1547-dns_consistency-no_report_id-0.1.0-probe.yaml
                end = blob.find("\n", start)
                if end != -1:
                    start = end + 1
                else:
                    head = blob[start:]
            else:
                raise BrokenFrameError(bloboff + start, prefix)
    if head:
        raise TruncatedReportError(fd.tell() - len(head), head)


def stream_json_blobs(fd):
    head = ""
    for blob in iter(functools.partial(fd.read, 1048576), ""):
        bloboff = fd.tell() - len(blob)
        head, blob = "", head + blob
        start = 0
        while not head:
            if len(blob) == start:
                break
            elif blob[start] != "{":  # just a sanity check
                raise BrokenFrameError(bloboff + start, blob[start])
            end = blob.find("}\n", start)  # newline is NOT valid json!
            if end != -1:
                yield bloboff + start, blob[start : end + 1]
                start = end + 2
            else:
                head = blob[start:]
    if head:
        raise TruncatedReportError(fd.tell() - len(head), head)


def stream_yaml_reports(fd):  # NormaliseReport._yaml_report_iterator
    fd = stream_yaml_blobs(fd)
    off, header = fd.next()
    headsha = sha1(header)
    # XXX: bad header kills whole bucket
    header = yaml.load(header, Loader=CLoader)
    if not header.get("report_id"):
        start_time = datetime.fromtimestamp(header.get("start_time", 0))
        report_id = start_time.strftime("%Y%m%dT%H%M%SZ_")
        value_to_hash = header.get("probe_cc", "ZZ")
        value_to_hash += header.get("probe_asn", "AS0")
        value_to_hash += header.get("test_name", "invalid")
        value_to_hash += header.get("software_version", "0.0.0")
        probe_city = header.get("probe_city", "None")
        probe_city = (
            probe_city.encode("utf-8")
            if isinstance(probe_city, unicode)
            else str(probe_city)
        )  # u'Reykjav\xedk' in bucket 2014-02-20
        value_to_hash += probe_city
        report_id += "".join(
            string.ascii_letters[ord(x) % len(string.ascii_letters)]
            for x in hashlib.sha512(value_to_hash).digest()
        )[:50]
        header["report_id"] = report_id
    for off, entry in fd:
        entry_len = len(entry)
        esha = headsha.copy()
        esha.update(entry)
        esha = esha.digest()
        try:
            entry = yaml.load(entry, Loader=CLoader)
            if not entry:  # e.g. '---\nnull\n...\n'
                continue
            if "test_start_time" in entry and "test_start_time" in header:
                header.pop("test_start_time")
            entry.update(header)
            yield off, entry_len, esha, entry, None
        except Exception as exc:
            yield off, entry_len, esha, None, exc


def stream_json_reports(fd):  # NormaliseReport._json_report_iterator
    for off, entry in stream_json_blobs(fd):
        entry_len = len(entry)
        esha = sha1(entry).digest()
        try:
            yield off, entry_len, esha, ujson.loads(entry), None
        except Exception as exc:
            yield off, entry_len, esha, None, exc


def autoclave_measurements(report_iter, perma_fname):
    assert (
        BRIDGE_DB is not None
        and perma_fname.count("/") == 1
        and perma_fname[:2] == "20"
    )  # XXI century
    bucket = perma_fname.split("/", 1)[0]
    for off, entry_len, esha, entry, exc in report_iter:
        hashuuid = esha[:16]  # sha1 is 20 bytes
        esha = b64encode(esha)
        if exc is None:
            try:
                entry = NormaliseReport._normalise_entry(
                    entry, bucket, perma_fname, hashuuid
                )
                if entry["test_name"] == "tcp_connect":
                    entry = SanitiseReport._sanitise_tcp_connect(entry, BRIDGE_DB)
                elif entry["test_name"] == "bridge_reachability":
                    entry = SanitiseReport._sanitise_bridge_reachability(
                        entry, BRIDGE_DB
                    )
                yield off, entry_len, esha, ujson.dumps(entry), None
            except Exception as exc:
                yield off, entry_len, esha, "", exc
        else:
            yield off, entry_len, esha, "", exc


def autoclave_tar(inputfd, caninfo, metafd, outfd):
    # inputfd    - is read with something like `tar -I lz4`
    # caninfo    - decoded line from canned/index.json
    # metafd     - pipe to store metainformation to autoclaved/index.json.gz
    # outfd      - destination for raw data
    text_size = {_["textname"]: _["text_size"] for _ in caninfo["canned"]}
    text_sha1 = {_["textname"]: _["text_sha1"] for _ in caninfo["canned"]}
    stream_report = {".json": stream_json_reports, ".yaml": stream_yaml_reports}
    with ScopedPopen(["lz4", "-d"], stdin=inputfd, stdout=PIPE) as proc_lz4, closing(
        LZ4WriteFramedStream(outfd, metafd, {"filename": caninfo["filename"]})
    ) as tarsink, tarfile.open(mode="w", fileobj=tarsink) as tarout:

        tarfd = tarfile.open(mode="r:", fileobj=ReadStream(proc_lz4.stdout))
        for tin in tarfd:
            if text_size[tin.name] != tin.size:
                # tarfile module verifies that short read does not happen
                raise RuntimeError(
                    "Canned file size mismatch", text_size[tin.name], tin.size
                )
            del text_size[tin.name]

            # list is unrolled as `tin.size` must be updated before writing
            # file header. Only small files are compressed in the tar file,
            # so this code does not allocate zillion bytes of memory.
            report = []
            try:
                report_iter = stream_report[tin.name[-5:]](tarfd.extractfile(tin))
                for i in autoclave_measurements(report_iter, tin.name):
                    report.append(i)  # one by one, to handle truncation
                cutoff = None
                cut = None
            except BlobSlicerError as exc:
                cutoff, _ = exc.args
                cut = str(type(exc))

            newtin = tarfile.TarInfo(tin.name)
            newtin.mtime = EPOCH
            newtin.uname = "ooni"
            newtin.gname = "torproject"
            newtin.size = sum(
                len(_[3]) + 1 for _ in report if _[4] is None
            )  # blobs + newlines

            tarout.addfile(newtin)
            tarsink.write_both(
                "",
                {
                    "type": "report",
                    "textname": tin.name,
                    "src_size": tin.size,
                    "orig_sha1": text_sha1[tin.name],
                },
            )

            for off, entry_len, esha, entry, exc in report:
                if exc is None:
                    tarsink.write_both(entry, {"type": "datum", "orig_sha1": esha})
                    tarsink.write("\n")
                else:
                    tarsink.write_both(
                        "",
                        {
                            "type": "badblob",
                            "orig_sha1": esha,
                            "src_off": off,
                            "src_size": entry_len,
                            "info": str(type(exc)),
                        },
                    )

            tarfile_write_padding(tarout, newtin.size)
            if cut is None:
                tarsink.write_both("", {"type": "/report"})
            else:
                tarsink.write_both(
                    "", {"type": "/report", "src_cutoff": cutoff, "info": cut}
                )

        # `tarfile` does not read and verify padding, so there is no reason to
        # compare current offset with text_size of the file.
        if text_size:
            raise RuntimeError("Leftover files", text_size.keys())
        # {'type': '/file'} is written by LZ4WriteFramedStream.close


def autoclave_blob(inputfd, caninfo, metafd, outfd):
    textname = caninfo["textname"]
    stream_report = {".json": stream_json_reports, ".yaml": stream_yaml_reports}
    with ScopedPopen(["lz4", "-d"], stdin=inputfd, stdout=PIPE) as proc_lz4, closing(
        LZ4WriteFramedStream(outfd, metafd, {"filename": caninfo["filename"]})
    ) as sink:

        source = ReadStream(proc_lz4.stdout)  # to account number of read bytes
        sink.write_both(
            "",
            {
                "type": "report",
                "textname": textname,
                "src_size": caninfo["text_size"],
                "orig_sha1": caninfo["text_sha1"],
            },
        )
        try:
            report_iter = stream_report[textname[-5:]](source)
            for off, entry_len, esha, entry, exc in autoclave_measurements(
                report_iter, textname
            ):
                if exc is None:
                    sink.write_both(entry, {"type": "datum", "orig_sha1": esha})
                    sink.write("\n")
                else:
                    sink.write_both(
                        "",
                        {
                            "type": "badblob",
                            "orig_sha1": esha,
                            "src_off": off,
                            "src_size": entry_len,
                            "info": str(type(exc)),
                        },
                    )
            sink.write_both("", {"type": "/report"})
        except BlobSlicerError as exc:
            cutoff, _ = exc.args
            sink.write_both(
                "", {"type": "/report", "src_cutoff": cutoff, "info": str(type(exc))}
            )
        if source.tell() != caninfo["text_size"]:
            raise RuntimeError(
                "Unexpected number of bytes from lz4 pipe",
                source.tell(),
                caninfo["text_size"],
            )
        # {'type': '/file'} is written by LZ4WriteFramedStream.close


def verify_index(index_fpath, bucket, in_files, out_dir):
    out_size = {
        "{}/{}".format(bucket, f): sz
        for f, sz in listdir_filesize(out_dir)
        if f != INDEX_FNAME
    }
    ondisk_size = filename = None
    with gzip.GzipFile(index_fpath, "r") as fd:
        # stream_json_blobs and substring pre-filter gives ~3x speedup, not a big deal
        # for index verification, but `tarfile` already payed for it, so... :)
        for off, line in stream_json_blobs(fd):
            if 'file"' in line:
                doc = ujson.loads(line)
                if doc["type"] == "file":
                    if ondisk_size is not None:
                        raise RuntimeError("Corrupt index file", index_fpath, doc)
                    filename = doc["filename"]
                    in_files.remove(filename)
                    ondisk_size = out_size.pop(filename)
                elif doc["type"] == "/file":
                    if doc["file_size"] != ondisk_size:
                        raise RuntimeError(
                            "Mismatching sizes for autoclaved file",
                            filename,
                            ondisk_size,
                            doc["file_size"],
                        )
                    ondisk_size = filename = None
    if in_files:
        raise RuntimeError("Leftover canned & not autoclaved files", sorted(in_files))
    if out_size:
        raise RuntimeError(
            "Leftover autoclaved files non in {}".format(INDEX_FNAME),
            sorted(out_size.keys()),
        )


def autoclaving(in_root, out_root, bucket):
    assert in_root[-1] != "/" and out_root[-1] != "/" and "/" not in bucket
    in_dir = dirname(os.path.join(in_root, bucket))
    out_dir = dirname(os.path.join(out_root, bucket))
    # Bucket MUST exist as single bucket is mounted to data processing container.
    index_fpath = os.path.join(out_dir, INDEX_FNAME)
    if os.path.exists(index_fpath):  # verify if everything is OK or die
        in_files = {
            "{}/{}".format(bucket, f)
            for f in os.listdir(in_dir)
            if f != canning.INDEX_FNAME
        }
        verify_index(index_fpath, bucket, in_files, out_dir)
        print "The bucket {} is already canned".format(bucket)
        return

    canindex = canning.load_verified_index(in_dir, bucket)
    with tmp.open_tmp_gz(index_fpath, chmod=0444) as metafd:
        for caninfo in canindex:
            with open(
                os.path.join(in_root, caninfo["filename"]), "rb"
            ) as inputfd, tmp.open_tmp(
                os.path.join(out_root, caninfo["filename"]), chmod=0444
            ) as outfd:
                if "canned" in caninfo:
                    autoclave_tar(inputfd, caninfo, metafd, outfd)
                else:
                    autoclave_blob(inputfd, caninfo, metafd, outfd)
    os.chmod(out_dir, 0555)  # done!


def autoclaving_missing(in_root, out_root, bucket):
    with open(os.path.join(in_root, bucket, canning.INDEX_FNAME)) as fd:
        canindex = can.load_index(fd)
    needed = {
        caninfo["filename"]
        for caninfo in canindex
        if not os.path.exists(os.path.join(out_root, caninfo["filename"]))
    }
    for filename in needed:
        if not os.path.exists(os.path.join(in_root, filename)):
            RuntimeError("Source file missing", in_root, bucket, filename)
    in_dir = dirname(os.path.join(in_root, bucket))
    out_dir = dirname(os.path.join(out_root, bucket))
    index_fpath = os.path.join(out_root, bucket, INDEX_FNAME)
    if not needed:
        in_files = {caninfo["filename"] for caninfo in canindex}
        verify_index(index_fpath, bucket, in_files, out_dir)
        print "The bucket {} has no missing files".format(bucket)
        return

    with tmp.ScopedTmpdir(dir=out_dir) as tmpdir:
        with tmp.open_tmp_gz(os.path.join(tmpdir, INDEX_FNAME), chmod=0444) as out_ndx:
            with gzip.GzipFile(os.path.join(out_dir, INDEX_FNAME), "r") as in_ndx:
                doc_stream = stream_json_blobs(in_ndx)
                for offset, line in doc_stream:
                    doc = ujson.loads(line)
                    if doc["type"] != "file":
                        raise RuntimeError(
                            "Expected type:file in index", out_dir, offset, doc
                        )
                    copy = doc["filename"] not in needed
                    if copy:
                        out_ndx.write(line + "\n")
                    for offset, line in doc_stream:
                        if copy:
                            out_ndx.write(line + "\n")
                        if 'file"' in line and ujson.loads(line)["type"] == "/file":
                            break  # handle next file
            for caninfo in canindex:
                filename = caninfo["filename"]
                if filename in needed:
                    with open(
                        os.path.join(in_root, filename), "rb"
                    ) as inputfd, tmp.open_tmp(
                        os.path.join(tmpdir, os.path.basename(filename)), chmod=0444
                    ) as outfd:
                        if "canned" in caninfo:
                            autoclave_tar(inputfd, caninfo, out_ndx, outfd)
                        else:
                            autoclave_blob(inputfd, caninfo, out_ndx, outfd)
        os.link(
            index_fpath, index_fpath + "~"
        )  # to have failflag & backup in case of failure
        os.rename(os.path.join(tmpdir, INDEX_FNAME), index_fpath)
        for filename in needed:
            os.link(
                os.path.join(tmpdir, os.path.basename(filename)),
                os.path.join(out_root, filename),
            )
        os.unlink(index_fpath + "~")
    os.chmod(out_dir, 0555)  # done!


def parse_args():
    p = argparse.ArgumentParser(
        description="ooni-pipeline: private/canned -> public/autoclaved"
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
        "--canned-root",
        metavar="DIR",
        type=dirname,
        help="Path to .../private/canned",
        required=True,
    )
    p.add_argument(
        "--autoclaved-root",
        metavar="DIR",
        type=dirname,
        help="Path to .../public/autoclaved",
        required=True,
    )
    p.add_argument(
        "--bridge-db",
        metavar="PATH",
        type=file,
        help="Path to .../private/bridge_db.json",
        required=True,
    )
    p.add_argument(
        "--missing",
        action="store_true",
        help="Handle `canned' missing from `autoclaved' to prepare for reingestion",
    )
    opt = p.parse_args()
    if (opt.end - opt.start) != timedelta(days=1):
        p.error("The script processes 24h batches")
    return opt


def main():
    # autoclaved/index.json.gz is compressed as …
    # - gzip has crc & size check, so there is no need in explicit eof
    # - in some pathological cases size of uncompressed index.json equals size of compressed xx.tar.lz4
    # with gzip and not lz4 as …
    # - python-lz4 streaming reader is not done yet (gzip requires seek()-able file, but python-lz4 can't even do that)
    # - gzip is ~75% of lz4 size (not a big deal, though)

    # tar read | split-reports | jsonize-normalize-sanitize | tar write | lz4
    opt = parse_args()
    with closing(opt.bridge_db) as fd:
        global BRIDGE_DB
        BRIDGE_DB = ujson.load(fd)
    bucket = opt.start.strftime("%Y-%m-%d")
    if not opt.missing:
        autoclaving(opt.canned_root, opt.autoclaved_root, bucket)
    else:
        autoclaving_missing(opt.canned_root, opt.autoclaved_root, bucket)


if __name__ == "__main__":
    main()
