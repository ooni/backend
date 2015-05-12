from __future__ import absolute_import, print_function, unicode_literals

import time
import random
import string
import traceback
from datetime import datetime
import yaml

from streamparse.spout import Spout

from helpers import sanitise
from helpers.settings import config


class Report(object):
    _end_time = None
    _start_time = None

    def __init__(self, in_file):
        self.in_file = in_file
        self.open()

    def failure(self, traceback, state):
        print("Fail in %s" % state)
        print(traceback)

    def open(self):
        self._start_time = time.time()
        self.in_fh = self.in_file.open("r")

        self._report = yaml.safe_load_all(self.in_fh)
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
        header_entry["record_type"] = "report_header"

        self._sanitised_header = self.sanitise_header(header_entry)

    def sanitise_entry(self, entry):
        # XXX we probably want to ignore these sorts of tests
        if not self._sanitised_header.get('test_name'):
            self.failure("MISSING TEST_NAME", "sanitise_entry")
            return entry
        return sanitise.run(self._raw_header['test_name'], entry)

    def process_entry(self, entry):
        entry["record_type"] = "measurement"

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
            'signature': 'XXX',
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
                self.done()
                break
            except Exception:
                self.failure(traceback.format_exc(), "process_entry")


class ReportStreamEmitter(object):
    def __init__(self):
        self.connect_to_s3()

    def connect_to_s3(self):
        from boto.s3.connection import S3Connection
        ACCESS_KEY_ID = config["aws"]["access-key-id"]
        SECRET_ACCESS_KEY = config["aws"]["secret-access-key"]
        BUCKET_NAME = config["aws"]["s3-bucket-name"]
        self.s3_connection = S3Connection(ACCESS_KEY_ID, SECRET_ACCESS_KEY)
        self.bucket = self.s3_connection.get_bucket(BUCKET_NAME)

    def parse(self, report_file):
        with report_file.open('r') as in_file:
            report = Report(in_file)
            yield report.header['sanitised'], report.header['raw']
            for sanitised_report, raw_report in report.process():
                yield sanitised_report, raw_report
            yield report.footer['sanitised'], report.footer['raw']

    def emit(self):
        for report in self.next_report():
            for sanitised_report, raw_report in self.parse():
                yield sanitised_report, raw_report

    def next_report(self):
        for key in self.bucket.list('reports'):
            yield key


class S3ReportsSpout(Spout):

    def initialize(self, stormconf, context):
        self.report_emitter = ReportStreamEmitter()
        self.reports = self.report_emitter.emit()

    def next_tuple(self):
        sanitised_report, raw_report = next(self.reports)
        report_id = sanitised_report['report_id']
        self.emit([report_id, sanitised_report])
