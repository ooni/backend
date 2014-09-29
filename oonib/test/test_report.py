import os
import json
import yaml

from twisted.internet import defer

from cyclone import web

from oonib.report.handlers import report_file_name
from oonib.report.api import reportAPI
from oonib.test.handler_helpers import HandlerTestCase, mock_initialize

sample_report_entry = """---
agent: agent
input: null
requests:
- request:
    body: null
    headers:
    - - ACCePT-LAnGuagE
    - ['en-US,en;q=0.8']
    - - aCCEPT-ENcODInG
    - ['gzip,deflate,sdch']
    - - aCcEPT
    - ['text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8']
    - - User-AGeNt
    - ['Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.7) Gecko/20091221
        Firefox/3.5.7']
    - - aCCEpt-cHArSEt
    - ['ISO-8859-1,utf-8;q=0.7,*;q=0.3']
    - - HOsT
    - [KIXnnZDJfGKRNab.com]
    method: GET
    url: http://12.34.56.78
response:
    body: '{"headers_dict": {"ACCePT-LAnGuagE": ["en-US,en;q=0.8"], "aCCEPT-ENcODInG":
    ["gzip,deflate,sdch"], "HOsT": ["KIXnnZDJfGKRNab.com"], "aCcEPT": ["text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"],
    "User-AGeNt": ["Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.7)
    Gecko/20091221 Firefox/3.5.7"], "aCCEpt-cHArSEt": ["ISO-8859-1,utf-8;q=0.7,*;q=0.3"],
    "Connection": ["close"]}, "request_line": "GET / HTTP/1.1", "request_headers":
    [["Connection", "close"], ["ACCePT-LAnGuagE", "en-US,en;q=0.8"], ["aCCEPT-ENcODInG",
    "gzip,deflate,sdch"], ["aCcEPT", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"],
    ["User-AGeNt", "Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.7)
    Gecko/20091221 Firefox/3.5.7"], ["aCCEpt-cHArSEt", "ISO-8859-1,utf-8;q=0.7,*;q=0.3"],
    ["HOsT", "KIXnnZDJfGKRNab.com"]]}'
    code: 200
    headers: []
socksproxy: null
tampering:
header_field_name: false
header_field_number: false
header_field_value: false
header_name_capitalization: false
header_name_diff: []
request_line_capitalization: false
total: false
...
"""

sample_report_header = """---
input_hashes: []
options: []
probe_asn: AS0
probe_cc: ZZ
probe_city: null
probe_ip: 127.0.0.1
software_name: ooniprobe
software_version: 1.1.0
start_time: 0
test_name: fake_test
test_version: 0.1.0
...
"""

for _, handler in reportAPI:
    handler.initialize = mock_initialize


class TestReport(HandlerTestCase):
    app = web.Application(reportAPI, name='reportAPI')

    @defer.inlineCallbacks
    def update_report(self, report_id, content=sample_report_entry):
        data = {
            'content': content
        }
        response = yield self.request(
            '/report/%s' % report_id,
            "POST", data)
        defer.returnValue(response)


    @defer.inlineCallbacks
    def test_create_valid_report(self):
        data = {
            'software_name': 'ooni-test',
            'software_version': '0.1',
            'test_name': 'some-test',
            'test_version': '0.1',
            'probe_asn': 'AS0'
        }
        response = yield self.request('/report', "POST", data)
        response_body = json.loads(response.body)
        self.assertIn('backend_version', response_body)
        self.assertIn('report_id', response_body)
        self.filenames.add(response_body['report_id'])

    @defer.inlineCallbacks
    def test_create_valid_report_with_content(self):
        data = {
            'software_name': 'ooni-test',
            'software_version': '0.1',
            'test_name': 'some-test',
            'test_version': '0.1',
            'probe_asn': 'AS0',
            'content': sample_report_header
        }
        response = yield self.request('/report', "POST", data)
        response_body = json.loads(response.body)
        self.assertIn('backend_version', response_body)
        self.assertIn('report_id', response_body)
        self.filenames.add(response_body['report_id'])

    @defer.inlineCallbacks
    def test_create_invalid_report(self):
        data = {
            'software_name': 'ooni-test',
            'software_version': '0.1',
            'test_name': 'some-test',
            'test_version': '0.1',
            'probe_asn': 'XXX'
        }
        response = yield self.request('/report', "POST", data)
        response_body = json.loads(response.body)
        self.assertIn('error', response_body)
        self.assertEqual(response_body['error'],
                         'invalid-request-field probe_asn')

    @defer.inlineCallbacks
    def test_create_and_update_report(self):
        report_header = {
            'software_name': 'ooni-test',
            'software_version': '0.1',
            'test_name': 'some-test',
            'test_version': '0.1',
            'probe_asn': 'AS0'
        }
        response = yield self.request('/report', "POST", report_header)
        response_body = json.loads(response.body)
        self.assertIn('backend_version', response_body)
        self.assertIn('report_id', response_body)

        report_id = response_body['report_id']
        response = yield self.update_report(report_id)
        response_body = json.loads(response.body)

        with open(report_id) as f:
            self.filenames.add(report_id)
            written_report = yaml.safe_load_all(f)

            written_report_header = written_report.next()
            for key in report_header.keys():
                self.assertEqual(written_report_header[key], report_header[key])
            self.assertEqual(yaml.safe_load(sample_report_entry),
                             written_report.next())

    @defer.inlineCallbacks
    def test_create_update_and_close_report(self):
        report_header = {
            'software_name': 'ooni-test',
            'software_version': '0.1',
            'test_name': 'some-test',
            'test_version': '0.1',
            'probe_asn': 'AS0'
        }
        response = yield self.request('/report', "POST", report_header)
        response_body = json.loads(response.body)
        self.assertIn('backend_version', response_body)
        self.assertIn('report_id', response_body)

        report_entry_count = 100

        report_id = response_body['report_id']
        for i in range(report_entry_count):
            yield self.update_report(report_id)

        with open(report_id) as f:
            written_report = yaml.safe_load_all(f)

            written_report_header = written_report.next()
            for key in report_header.keys():
                self.assertEqual(written_report_header[key],
                                 report_header[key])

            self.assertEqual(yaml.safe_load(sample_report_entry),
                             written_report.next())

        response = yield self.request('/report/%s/close' % report_id, "POST")

        written_report_path = report_file_name(".", written_report_header)
        with open(written_report_path) as f:
            self.filenames.add(written_report_path)
            written_report = yaml.safe_load_all(f)
            written_report.next()

            for i in range(report_entry_count):
                self.assertEqual(yaml.safe_load(sample_report_entry),
                                 written_report.next())

        self.directories.add('ZZ')
