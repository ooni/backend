from __future__ import absolute_import, print_function, unicode_literals

import os
import time
import random
import string
import logging
import traceback
from datetime import datetime

import yaml
# dns_consistency tests use [8.8.8.8, 53] as key in a dict
def construct_yaml_map(loader, node):
    pairs = [(str(key) if isinstance(key, list) else key, value)
            for (key, value) in loader.construct_pairs(node, deep=True)]
    return dict(pairs)
yaml.SafeLoader.add_constructor(u'tag:yaml.org,2002:map', construct_yaml_map)
from pipeline.helpers import sanitise

logger = logging.getLogger('ooni-pipeline')

mappings = {
    "http_host": ["http_template", "http_host"],
    "HTTP Host": ["http_template", "http_host"],

    "http_requests_test": ["http_template",
                           "http_requests"],
    "http_requests": ["http_template", "http_requests"],
    "HTTP Requests Test": ["http_template",
                           "http_requests"],

    "bridge_reachability": ["bridge_reachability"],
    "bridgereachability": ["bridge_reachability"],

    "TCP Connect": ["tcp_connect"],
    "tcp_connect": ["tcp_connect"],

    "DNS tamper": ["dns_template", "dns_consistency"],
    "dns_consistency": ["dns_template", "dns_consistency"],

    "HTTP Invalid Request Line": ["tcp_connect", "http_invalid_request_line"],
    "http_invalid_request_line": ["tcp_connect", "http_invalid_request_line"],

    "http_header_field_manipulation": ["http_header_field_manipulation"],
    "HTTP Header Field Manipulation": ["http_header_field_manipulation"],

    "Multi Protocol Traceroute Test": ["scapy_template", "multi_protocol_traceroute"],
    "multi_protocol_traceroute_test": ["scapy_template", "multi_protocol_traceroute"],
    "traceroute": ["scapy_template", "multi_protocol_traceroute"],

    "parasitic_traceroute_test": ["scapy_template"],

    "tls-handshake": ["tls_handshake"],

    "dns_injection": ["scapy_template", "dns_injection"],

    "captivep": ["captive_portal"],
    "captiveportal": ["captive_portal"],

    # These are ignored as we don't yet have analytics for them
    "HTTPFilteringBypass": False,
    "HTTPTrix": False,
    "http_test": False,
    "http_url_list": False,
    "dns_spoof": False,
    "netalyzrwrapper": False,

    # These are ignored because not code for them is available
    "tor_http_requests_test": False,
    "sip_requests_test": False,
    "tor_exit_ip_test": False,
    "website_probe": False,
    "base_tcp_test": False,

    # These are ignored because they are invalid reports
    "summary": False,
    "test_get": False,
    "test_put": False,
    "test_post": False,
    "this_test_is_nameless": False,
    "test_send_host_header": False,
    "test_random_big_request_method": False,
    "test_get_random_capitalization": False,
    "test_put_random_capitalization": False,
    "test_post_random_capitalization": False,
    "test_random_invalid_field_count": False,
    "keyword_filtering_detection_based_on_rst_packets": False
}


header_avro = {
    "type": "record",
    "name": "ReportHeader",
    "fields": [
        {"name": "backend_version", "type": "string"},
        {"name": "input_hashes", "type": "array", "items": "string"},
        {"name": "options", "type": "string"},
        {"name": "probe_asn", "type": "string"},
        {"name": "probe_cc", "type": "string"},
        {"name": "probe_ip", "type": "string"},
        {"name": "record_type", "type": "string"},
        {"name": "report_filename", "type": "string"},
        {"name": "report_id", "type": "string"},
        {"name": "software_name", "type": "string"},
        {"name": "software_version", "type": "string"},
        {"name": "start_time", "type": "string"},
        {"name": "test_name", "type": "string"},
        {"name": "test_version", "type": "string"},
        {"name": "data_format_version", "type": "string"},
        {"name": "test_helpers", "type": "string"}
    ]
}

class Report(object):
    def __init__(self, in_file, bridge_db, path):
        self.bridge_db = bridge_db
        self._start_time = time.time()
        self._end_time = None
        self._skipped_line = 0

        self.in_file = in_file
        self.filename = os.path.basename(path)
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
        try:
            self._raw_header = report.next()
        except StopIteration:
            return
        self._raw_header["record_type"] = "header"
        self._raw_header["report_filename"] = self.filename

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
            logger.error("test_name is missing in %s" % entry["report_id"])
            return entry
        return sanitise.run(self._raw_header['test_name'], entry, self.bridge_db)

    def add_record_type(self, entry):
        entry["record_type"] = "entry"
        return entry

    def process_entry(self, entry):
        if 'report' in entry:
            entry.update(entry.pop('report'))
        raw_entry = entry.copy()
        sanitised_entry = entry.copy()

        raw_entry.update(self._raw_header)
        sanitised_entry.update(self._sanitised_header)

        raw_entry = self.add_record_type(raw_entry)
        sanitised_entry = self.add_record_type(sanitised_entry)

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
                self._end_time = time.time()
                print("failed to process the entry for %s" % self.filename)
                print(traceback.format_exc())
                raise exc
        self._end_time = time.time()
