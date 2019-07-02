#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# That's a sanity check to ensure that we can migrate from historical public/sanitised to public/autoclaved:
# 1. every sanitised/ file is in autoclaved/
# 2. every sanitised/ file almost equals corresponding autoclaved/
# 3. DOES NOT check that every autoclaved/ is in sanitised/ (that's not true as some reports-raw were never sanitised)
#
# This sanity check means that sanitised/ is safe to delete.

import argparse
import datetime
import gzip
import hashlib
import os
import tempfile
from functools import partial

import ujson
import lz4.frame as lz4frame

import autoclaving
from oonipl.cli import dirname

FILE_START, FILE_END, REPORT_START, REPORT_END, BADBLOB, DATUM = (
    object(),
    object(),
    object(),
    object(),
    object(),
    object(),
)


def stream_datum(atclv_root, bucket, take_file=None):
    with gzip.GzipFile(
        os.path.join(atclv_root, bucket, autoclaving.INDEX_FNAME), "r"
    ) as indexfd:
        filefd = None
        dociter = autoclaving.stream_json_blobs(indexfd)
        for _, doc in dociter:
            doc = ujson.loads(doc)
            t = doc["type"]
            if t == "datum":
                # {"orig_sha1": "q7…I=", "text_off": 156846, "text_size": 58327, "type": "datum"}
                intra_off = doc["text_off"] - text_off
                datum = blob[intra_off : intra_off + doc["text_size"]]
                assert intra_off >= 0 and len(datum) == doc["text_size"]
                datum = ujson.loads(datum)
                doc["frame_off"] = frame_off
                doc["frame_size"] = frame_size
                doc["intra_off"] = intra_off
                doc["intra_size"] = doc["text_size"]
                doc["datum"] = datum
                yield DATUM, doc
                del intra_off, datum

            elif t == "frame":
                # {"file_off": 0, "file_size": 162864, "text_off": 0, "text_size": 362462, … }
                frame_off, frame_size = doc["file_off"], doc["file_size"]
                assert filefd.tell() == frame_off
                blob = filefd.read(frame_size)
                assert len(blob) == frame_size
                blob = lz4frame.decompress(blob)
                assert len(blob) == doc["text_size"]
                text_off = doc["text_off"]

            elif t == "/frame":
                del frame_off, frame_size, text_off, blob

            elif t == "report":
                # {"orig_sha1": "HO…U=",
                #  "src_size": 104006450,
                #  "textname": "2017-01-01/20161231T000030Z-US-AS…-0.2.0-probe.json", …}
                yield REPORT_START, doc

            elif t == "/report":
                # {"info": "<class '__main__.TruncatedReportError'>",
                #  "src_cutoff": 49484700, … }
                yield REPORT_END, doc

            elif t == "file":
                # {"filename": "2017-01-01/20161231T000030Z-US-AS…-0.2.0-probe.json.lz4", …}
                filename = doc["filename"]
                assert filename.startswith(bucket)
                if take_file is None or take_file(filename):
                    filefd = open(os.path.join(atclv_root, filename), "rb")
                    del filename
                    yield FILE_START, doc
                else:
                    for _, skipdoc in dociter:
                        if (
                            '/file"' in skipdoc
                            and ujson.loads(skipdoc)["type"] == "/file"
                        ):
                            break
                    del filename, skipdoc

            elif t == "/file":
                # {"file_crc32": -156566611, "file_sha1": "q/…8=", "file_size": 18132131, …}
                assert filefd.tell() == doc["file_size"]
                filefd.close()
                filefd = None
                yield FILE_END, doc

            elif t == "badblob":
                # {"orig_sha1": "RXQFwOtpKtS0KicYi8JnWeQYYBw=",
                #  "src_off": 99257, "src_size": 238,
                #  "info": "<class 'yaml.constructor.ConstructorError'>", …}
                yield BADBLOB, doc

            else:
                raise RuntimeError("Unknown record type", t)
        if filefd is not None:
            raise RuntimeError("Truncated autoclaved index", atclv_root, bucket)


def parse_time(s):
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def calc_santoken(sanitised_root, autoclaved_root, bucket):
    known_sanitised = sorted(
        "{}/{}".format(bucket, _)
        for _ in os.listdir(os.path.join(sanitised_root, bucket))
    )
    santoken = hashlib.sha1()
    with open(
        os.path.join(autoclaved_root, bucket, autoclaving.INDEX_FNAME), "rb"
    ) as fd:
        for blob in iter(partial(fd.read, 1048576), ""):
            santoken.update(blob)
    santoken.update("\0".join(known_sanitised))
    return santoken.hexdigest()


def check_sanitised(autoclaved_root, sanitised_root, bucket):
    san_obj, auto_obj = object(), object()
    # FIXME: it's technicaly a race condition :)
    santoken = calc_santoken(sanitised_root, autoclaved_root, bucket)
    known_sanitised = set(
        "{}/{}".format(bucket, _)
        for _ in os.listdir(os.path.join(sanitised_root, bucket))
    )
    datum_iter = stream_datum(autoclaved_root, bucket)
    for ev, doc in datum_iter:
        assert ev is FILE_START
        for ev, doc in datum_iter:
            if ev is FILE_END:
                break
            assert ev is REPORT_START
            textname = doc["textname"]
            autoclaved_textname = (
                textname
            )  # textname is also key for `known_sanitised`, this var is kept intact
            if textname.endswith(".yaml"):
                textname = textname[:-5] + ".json"
            sanpath = os.path.join(sanitised_root, textname)
            if os.path.exists(sanpath):
                saniter = autoclaving.stream_json_blobs(open(sanpath))
                for ev, doc in datum_iter:
                    if ev is DATUM:
                        san = ujson.loads(next(saniter)[1])
                        auto = doc["datum"]
                        diff = {
                            "metadata": {
                                "sanitised": textname,
                                "autoclaved": autoclaved_textname,
                                "autoclaved_orig_sha1": doc["orig_sha1"],
                            },
                            "sanitised": {},
                            "autoclaved": {},
                        }

                        del san["id"], auto["id"]  # it was random

                        # wrong TZ during sanitisation, autoclaved enforces UTC
                        if san["test_start_time"] != auto["test_start_time"]:
                            if san["test_start_time"].startswith(
                                "1970-01-01 "
                            ):  # something like 1970-01-01 01:00:00
                                diff["sanitised"]["test_start_time"] = san.pop(
                                    "test_start_time"
                                )
                                diff["autoclaved"]["test_start_time"] = auto.pop(
                                    "test_start_time"
                                )
                            else:
                                dt = parse_time(san["test_start_time"]) - parse_time(
                                    auto["test_start_time"]
                                )
                                if (
                                    dt.days == 0 and (dt.seconds % 3600) == 0
                                ):  # something like 2016-12-31 07:26:22 vs. 2016-12-31 06:26:22
                                    diff["sanitised"]["test_start_time"] = san.pop(
                                        "test_start_time"
                                    )
                                    diff["autoclaved"]["test_start_time"] = auto.pop(
                                        "test_start_time"
                                    )
                            # `report_id` may use test_start_time as prefix: 20161231T072622Z_MhNAwTSRMIyWmzudgbdteCPUNUpzaShRsfBvCfzLePvbeHGcWF
                            if (
                                san["report_id"] != auto["report_id"]
                                and "test_start_time" in diff["sanitised"]
                                and "Z_" in san["report_id"]
                            ):
                                diff["sanitised"]["report_id"] = san["report_id"]
                                diff["autoclaved"]["report_id"] = auto["report_id"]
                                san["report_id"] = san["report_id"].split("Z_", 1)[1]
                                auto["report_id"] = auto["report_id"].split("Z_", 1)[1]
                        if (
                            san["measurement_start_time"]
                            != auto["measurement_start_time"]
                        ):  # another wrong TZ
                            dt = parse_time(san["measurement_start_time"]) - parse_time(
                                auto["measurement_start_time"]
                            )
                            if dt.days == 0 and (dt.seconds % 3600) == 0:
                                # something like 2016-12-31 07:26:34 vs 2016-12-31 06:26:34
                                diff["sanitised"]["measurement_start_time"] = san.pop(
                                    "measurement_start_time"
                                )
                                diff["autoclaved"]["measurement_start_time"] = auto.pop(
                                    "measurement_start_time"
                                )

                        # `autoclaved` preserves `.yaml` extention is `report_filename`, `sanitised` replaces with `.json`
                        if (
                            san["report_filename"] != auto["report_filename"]
                            and auto["report_filename"][-5:] == ".yaml"
                        ):
                            diff["sanitised"]["report_filename"] = san[
                                "report_filename"
                            ]
                            diff["autoclaved"]["report_filename"] = auto[
                                "report_filename"
                            ]
                            auto["report_filename"] = (
                                auto["report_filename"][:-5] + ".json"
                            )

                        # that's some useless(?) empty list in `sanitised`
                        for k in ("sent", "received"):
                            if k in san and k not in auto and san[k] == []:
                                del san[k]

                        for k in san.keys():
                            if san.get(k, san_obj) == auto.get(k, auto_obj):
                                del san[k], auto[k]
                        if diff["sanitised"]:
                            print "OKAYISH-DIFF:", ujson.dumps(diff)
                        if san != doc["datum"]:
                            raise RuntimeError(textname, "mismatch", san, doc["datum"])

                    elif ev is BADBLOB:
                        pass
                    elif ev is REPORT_END:
                        if next(saniter, None) is not None:
                            raise RuntimeError(textname, "leftover in sanitised")
                        known_sanitised.remove(textname)
                        break
                    else:
                        raise RuntimeError("Unexpected event type", doc["type"])
            else:  # okay, no corresponding sanitised file
                for ev, _ in datum_iter:
                    # wasting cycles in reading and decompression
                    if ev is REPORT_END:
                        break
                    elif ev not in (DATUM, BADBLOB):
                        raise RuntimeError("Unexpected event type", doc["type"])
            assert ev is REPORT_END
        assert ev is FILE_END
    if known_sanitised:
        raise RuntimeError("Some sanitised files are not autoclaved", known_sanitised)
    return santoken


def parse_args():
    p = argparse.ArgumentParser(
        description="ooni-pipeline: verify that public/autoclaved contains public/sanitised"
    )
    p.add_argument("--bucket", metavar="BUCKET", help="Bucket to check", required=True)
    p.add_argument(
        "--sanitised-root",
        metavar="DIR",
        type=dirname,
        help="Path to .../public/sanitised",
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
        "--santoken",
        metavar="FILE",
        help="Token for checked sanitised directory",
        required=True,
    )
    opt = p.parse_args()
    # that's not `os.path.join` to verify _textual_ value of the option
    dirname("{}/{}".format(opt.sanitised_root, opt.bucket))
    dirname("{}/{}".format(opt.autoclaved_root, opt.bucket))
    return opt


def main():
    opt = parse_args()

    if os.path.exists(opt.santoken):
        with open(opt.santoken) as fd:
            stored_santoken = fd.read()
        santoken = calc_santoken(opt.sanitised_root, opt.autoclaved_root, opt.bucket)
        if stored_santoken == santoken:
            print "santoken is up to date"
            return
        else:
            raise RuntimeError(
                "Stale santoken exists", opt.santoken, stored_santoken, santoken
            )

    with tempfile.NamedTemporaryFile(
        prefix="tmpst", dir=os.path.dirname(opt.santoken)
    ) as fd:
        santoken = check_sanitised(opt.autoclaved_root, opt.sanitised_root, opt.bucket)
        fd.write(santoken)
        fd.flush()
        os.link(fd.name, opt.santoken)
    os.chmod(opt.santoken, 0444)


if __name__ == "__main__":
    main()
