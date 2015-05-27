from __future__ import absolute_import, print_function, unicode_literals

import time
import random
import string
import traceback
from datetime import datetime

import yaml
from pipeline.helpers import sanitise


class Report(object):
    def __init__(self, in_file):
        self._start_time = time.time()
        self._end_time = None
        self._skipped_line = 0

        self.in_file = in_file
        self._report = yaml.safe_load_all(self.in_file)
        self.process_header(self._report)

    def entries(self):
        yield self.header['sanitised'], self.header['raw']
        for sanitised_report, raw_report in self.process():
            yield sanitised_report, raw_report
        yield self.footer['sanitised'], self.footer['raw']

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
        self._raw_header["record_type"] = "header"

        date = datetime.fromtimestamp(self._raw_header["start_time"])
        date = date.strftime("%Y-%m-%d")
        if not self._raw_header.get("report_id"):
            nonce = ''.join(random.choice(string.ascii_lowercase)
                            for x in xrange(40))
            self._raw_header["report_id"] = date + nonce

        header_entry = self._raw_header.copy()

        self._sanitised_header = self.sanitise_header(header_entry)

    def sanitise_entry(self, entry):
        # XXX we probably want to ignore these sorts of tests
        if not self._sanitised_header.get('test_name'):
            print("MISSING TEST_NAME", "sanitise_entry")
            return entry
        return sanitise.run(self._raw_header['test_name'], entry)

    def process_entry(self, entry):
        raw_entry = entry.copy()
        sanitised_entry = entry.copy()

        raw_entry.update(self._raw_header)
        sanitised_entry.update(self._sanitised_header)

        raw_entry["record_type"] = "entry"
        sanitised_entry["record_type"] = "entry"

        sanitised_entry = self.sanitise_entry(sanitised_entry)
        return sanitised_entry, raw_entry

    @property
    def footer(self):
        raw = self._raw_header.copy()
        sanitised = self._sanitised_header.copy()

        process_time = None
        if self._end_time:
            process_time = self._end_time - self._start_time

        extra_keys = {
            'record_type': 'footer',
            'stage_1_process_time': process_time
        }

        raw.update(extra_keys)
        sanitised.update(extra_keys)

        return {
            "raw": raw,
            "sanitised": sanitised
        }

    def _restart_from_line(self, line_number):
        """
        This is used to skip to the specified line number in case of YAML
        parsing erorrs. We also add to self._skipped_line since the YAML parsed
        will consider the line count as relative to the start of the document.
        """
        self._skipped_line = line_number+self._skipped_line+1
        self.in_file.seek(0)
        for _ in xrange(self._skipped_line):
            self.in_file.readline()
        self._report = yaml.safe_load_all(self.in_file)

    def process(self):
        while True:
            try:
                entry = self._report.next()
                if not entry:
                    continue
                yield self.process_entry(entry)
            except StopIteration:
                break
            except Exception as exc:
                if hasattr(exc, 'problem_mark'):
                    self._restart_from_line(exc.problem_mark.line)
                else:
                    print("Failed in processing the entry")
                    print(traceback.format_exc())
                    raise exc
                continue
        self._end_time = time.time()
