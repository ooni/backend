import zlib
import time
import random
import string
import tempfile
import traceback
from datetime import datetime

import yaml

from helpers.settings import config
from helpers import sanitise


class Report(object):
    _end_time = None
    _start_time = None

    def __init__(self, in_file):
        self._start_time = time.time()

        self.in_file = in_file
        self._report = yaml.safe_load_all(self.in_file)
        self.process_header(self._report)

    def sanitise_header(self, entry):
        return entry

    @property
    def header(self):
        return {
            "raw": self._raw_header,
            "sanitised": self._sanitised_header
        }

    def process_header(self, report):
        self._raw_header = report.next()

        date = datetime.fromtimestamp(self._raw_header["start_time"])
        date = date.strftime("%Y-%m-%d")
        if not self._raw_header.get("report_id"):
            nonce = ''.join(random.choice(string.ascii_lowercase)
                            for x in xrange(40))
            self._raw_header["report_id"] = date + nonce

        header_entry = self._raw_header.copy()
        header_entry["record_type"] = "header"

        self._sanitised_header = self.sanitise_header(header_entry)

    def sanitise_entry(self, entry):
        # XXX we probably want to ignore these sorts of tests
        if not self._sanitised_header.get('test_name'):
            print("MISSING TEST_NAME", "sanitise_entry")
            return entry
        return sanitise.run(self._raw_header['test_name'], entry)

    def process_entry(self, entry):
        entry["record_type"] = "entry"

        raw_entry = entry.copy()
        sanitised_entry = entry.copy()

        raw_entry.update(self._raw_header)
        sanitised_entry.update(self._sanitised_header)
        sanitised_entry = self.sanitise_entry(sanitised_entry)
        return sanitised_entry, raw_entry

    @property
    def footer(self):
        raw = self._raw_header.copy()
        sanitised = self._sanitised_header.copy()
        if not self._end_time:
            self._end_time = time.time()

        extra_keys = {
            'record_type': 'footer',
            'stage_1_process_time': self._start_time - self._end_time
        }

        raw.update(extra_keys)
        sanitised.update(extra_keys)

        return {
            "raw": raw,
            "sanitised": sanitised
        }

    def process(self):
        while True:
            try:
                entry = self._report.next()
                if not entry:
                    continue
                yield self.process_entry(entry)
            except StopIteration:
                break


def uncompress_to_disk(report_file):
    CHUNK_SIZE = 2048
    decompressor = zlib.decompressobj(16+zlib.MAX_WBITS)
    f = tempfile.NamedTemporaryFile('wb', prefix='ooni-tmp', delete=False)
    path = f.name
    while True:
        chunk = report_file.read(CHUNK_SIZE)
        if not chunk:
            break
        f.write(decompressor.decompress(chunk))
    f.close()
    return path


class ReportStreamEmitter(object):
    def __init__(self, folder):
        self.folder = folder
        self.connect_to_s3()

    def connect_to_s3(self):
        from boto.s3.connection import S3Connection
        ACCESS_KEY_ID = config["aws"]["access-key-id"]
        SECRET_ACCESS_KEY = config["aws"]["secret-access-key"]
        BUCKET_NAME = config["aws"]["s3-bucket-name"]
        self.s3_connection = S3Connection(ACCESS_KEY_ID, SECRET_ACCESS_KEY)
        self.bucket = self.s3_connection.get_bucket(BUCKET_NAME)

    def parse(self, report_file):
        report_file.open('r')
        uncompressed_path = uncompress_to_disk(report_file)
        report_file.close()
        with open(uncompressed_path) as in_file:
            report = Report(in_file)
            yield report.header['sanitised'], report.header['raw']
            for sanitised_report, raw_report in report.process():
                yield sanitised_report, raw_report
            yield report.footer['sanitised'], report.footer['raw']

    def emit(self):
        for report_file in self.next_report():
            for sanitised_report, raw_report in self.parse(report_file):
                yield sanitised_report, raw_report

    def next_report(self):
        for key in self.bucket.list(self.folder):
            yield key
