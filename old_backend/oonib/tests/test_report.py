import json
import yaml

from copy import deepcopy

from twisted.python.filepath import FilePath
from twisted.internet import defer

from cyclone import web

from oonib.config import config
from oonib.report.handlers import report_file_path, checkForStaleReports
from oonib.report.handlers import closeReport
from oonib.report.api import reportAPI
from oonib.tests.handler_helpers import HandlerTestCase, mock_initialize, MockTime

# Version number testing
# ----------------------
#
# We need to test an array of version numbers ranging from super compliant
# with semver (mobile apps since v1.2.0) to very basic (e.g. 0.1, as used
# in some cases by ooni-probe test implementations).
#
# To emphasize this, I have refactored this regress test to put the
# various version numbers we use here at the beginning of file.
FULL_SEMVER_VERSION = "1.7.0-beta.1+11.7"
BASIC_SEMVER_VERSION = "1.7.0"
SIMPLE_VERSION = "1.0"

sample_report_entry = {
    'agent': 'agent',
    'input': 'http://example.com',
    'requests': [
        {
            'request': {
                'body': None,
                'headers': {
                    'Accept-Language': 'en-US,en;q=0.8',
                    'User-AGeNt': 'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.7) Gecko/20091221'
                },
                'method': 'GET',
                'url': 'http://example.com'
            },
            'response': {
                'body': 'widgets',
                'headers': []
            }
        }
    ],
    'test_specific_key': 'some value',
    'input_hashes': [],
    'options': [],
    'probe_asn': 'AS0',
    'probe_cc': 'ZZ',
    'probe_city': None,
    'probe_ip': '127.0.0.1',
    'software_name': 'ooniprobe',
    'software_version': FULL_SEMVER_VERSION,
    'test_start_time': '2016-01-01 12:34:56',
    'test_name': 'fake_test',
    'test_version': '0.1.0'
}

sample_report_entry_yaml = '---\n'
sample_report_entry_yaml += yaml.dump(sample_report_entry)
sample_report_entry_yaml += '...\n'

sample_report_header_yaml = """---
input_hashes: []
options: []
probe_asn: AS0
probe_cc: ZZ
probe_city: null
probe_ip: 127.0.0.1
software_name: ooniprobe
software_version: %s
test_start_time: '2016-01-01 12:34:56'
test_name: fake_test
test_version: 0.1.0
...
""" % BASIC_SEMVER_VERSION

dummy_data = {
    'software_name': 'ooni-test',
    'software_version': SIMPLE_VERSION,
    'test_name': 'some-test',
    'test_version': SIMPLE_VERSION,
    'probe_asn': 'AS0',
    'probe_cc': 'ZZ',
    'test_start_time': '2016-01-01 12:34:56'
}

probe_android_200 = {
    'software_name': 'ooniprobe-android',
    'software_version': '2.0.0',
    'test_name': 'web_connectivity',
    'test_version': '0.1.0',
    'probe_asn': 'AS0',
    'probe_cc': 'ZZ',
    'test_start_time': '2016-01-01 12:34:56'
}


for _, handler in reportAPI:
    handler.initialize = mock_initialize


class TestReport(HandlerTestCase):
    app = web.Application(reportAPI, name='reportAPI')

    @defer.inlineCallbacks
    def update_report(self, report_id, content=sample_report_entry_yaml,
                      format="yaml"):
        data = {
            'content': content,
            'format': format
        }
        response = yield self.request(
            '/report/%s' % report_id,
            "POST", data)
        defer.returnValue(response)


    @defer.inlineCallbacks
    def test_create_android_2_dot_00(self):
        response = yield self.request('/report', "POST", probe_android_200)
        response_body = json.loads(response.body)
        self.assertIn('error', response_body)
        self.assertEqual(response_body['error'], 'invalid-request-field software_version')

    @defer.inlineCallbacks
    def test_create_valid_report(self):
        response = yield self.request('/report', "POST", dummy_data)
        response_body = json.loads(response.body)
        self.assertIn('backend_version', response_body)
        self.assertIn('report_id', response_body)
        self.filenames.add(response_body['report_id'])

    @defer.inlineCallbacks
    def test_create_valid_report_with_content(self):
        data = deepcopy(dummy_data)
        data['content'] = sample_report_header_yaml
        response = yield self.request('/report', "POST", data)
        response_body = json.loads(response.body)
        self.assertIn('backend_version', response_body)
        self.assertIn('report_id', response_body)
        self.filenames.add(response_body['report_id'])

        closeReport(response_body['report_id'])

    @defer.inlineCallbacks
    def test_create_invalid_report(self):
        data = deepcopy(dummy_data)
        data['probe_asn'] = 'XXXINVALID'
        response = yield self.request('/report', "POST", data)
        response_body = json.loads(response.body)
        self.assertIn('error', response_body)
        self.assertEqual(response_body['error'],
                         'invalid-request-field probe_asn')

    @defer.inlineCallbacks
    def test_create_and_update_report(self):
        response = yield self.request('/report', "POST", dummy_data)
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
            for key in dummy_data.keys():
                self.assertEqual(written_report_header[key], dummy_data[key])
            self.assertEqual(yaml.safe_load(sample_report_entry_yaml),
                             written_report.next())

        closeReport(report_id)

    @defer.inlineCallbacks
    def test_create_update_and_close_report(self):
        response = yield self.request('/report', "POST", dummy_data)
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
            for key in dummy_data.keys():
                self.assertEqual(written_report_header[key],
                                 dummy_data[key])

            self.assertEqual(yaml.safe_load(sample_report_entry_yaml),
                             written_report.next())

        response = yield self.request('/report/%s/close' % report_id, "POST")

        written_report_header['format'] = 'yaml'
        written_report_path = report_file_path(FilePath("."),
                                               written_report_header,
                                               report_id)
        with written_report_path.open('r') as f:
            self.filenames.add(written_report_path.path)
            written_report = yaml.safe_load_all(f)
            written_report.next()

            for i in range(report_entry_count):
                self.assertEqual(yaml.safe_load(sample_report_entry_yaml),
                                 written_report.next())

    @defer.inlineCallbacks
    def test_create_update_and_close_report_json(self):
        report_header = dummy_data.copy()
        report_header['format'] = 'json'
        response = yield self.request('/report', "POST", report_header)
        response_body = json.loads(response.body)
        self.assertIn('backend_version', response_body)
        self.assertIn('report_id', response_body)

        report_entry_count = 100

        report_id = response_body['report_id']
        for i in range(report_entry_count):
            yield self.update_report(report_id,
                                     content=sample_report_entry,
                                     format="json")

        response = yield self.request('/report/%s/close' % report_id, "POST")

        written_report_path = report_file_path(FilePath("."),
                                               report_header,
                                               report_id)
        with written_report_path.open('r') as f:
            self.filenames.add(written_report_path.path)
            for line in f:
                written_report = json.loads(line)
                self.assertEqual(sample_report_entry, written_report)


    @defer.inlineCallbacks
    def test_create_update_reap(self):
        mock_time = MockTime()

        report_header = dummy_data.copy()
        report_header['format'] = 'json'
        response = yield self.request('/report', "POST", report_header)
        response_body = json.loads(response.body)
        self.assertIn('backend_version', response_body)
        self.assertIn('report_id', response_body)

        report_entry_count = 100

        report_id = response_body['report_id']
        for i in range(report_entry_count):
            yield self.update_report(report_id,
                                     content=sample_report_entry,
                                     format="json")

        mock_time.advance(config.main.stale_time + 1)
        delayed_call = checkForStaleReports(mock_time)
        delayed_call.cancel()

        written_report_path = report_file_path(FilePath("."),
                                               report_header,
                                               report_id)

        with written_report_path.open('r') as f:
            self.filenames.add(written_report_path.path)
            for line in f:
                written_report = json.loads(line)
                self.assertEqual(sample_report_entry, written_report)
