import shutil
import time
import yaml
import json
import os
import re

from twisted.internet import fdesc, reactor

from oonib import errors as e
from oonib.handlers import OONIBHandler
from oonib.policy.handlers import Policy

from datetime import datetime
from oonib import randomStr, otime, log, json_dumps
from oonib.config import config


def report_file_name(archive_dir, report_details,
                     report_id='no_report_id'):
    timestamp = datetime.fromtimestamp(report_details['start_time'])
    if report_details['format'] == 'json':
        ext = 'json'
    elif report_details['format'] == 'yaml':
        ext = 'yaml'
    else:
        ext = 'invalid'

    keys = dict(
        report_details.items(),
        iso8601_timestamp=otime.timestamp(timestamp),
        year=timestamp.strftime("%Y"),
        month=timestamp.strftime("%m"),
        day=timestamp.strftime("%d"),
        hour=timestamp.strftime("%H"),
        minute=timestamp.strftime("%M"),
        second=timestamp.strftime("%S"),
        ext=ext,
        report_id=report_id
    )
    report_file_template = "{iso8601_timestamp}-{test_name}-{report_id}-{probe_asn}-{probe_cc}-probe-0.2.0.{ext}"
    if config.main.get('report_file_template'):
        report_file_template = config.main['report_file_template']
    dst_filename = os.path.join(archive_dir, report_file_template.format(**keys))
    dst_dir = os.path.dirname(dst_filename)
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
    return dst_filename


class Report(object):
    delayed_call = None

    def __init__(self, report_id,
                 stale_time,
                 report_dir,
                 archive_dir,
                 reports,
                 report_details):
        self.report_id = report_id

        self.report_details = report_details

        self.stale_time = stale_time
        self.report_dir = report_dir
        self.archive_dir = archive_dir
        self.reports = reports

        self.refresh()

    def refresh(self):
        self.last_updated = time.time()
        if self.delayed_call:
            self.delayed_call.cancel()
        self.delayed_call = reactor.callLater(self.stale_time,
                                              self.stale_check)

    def stale_check(self):
        if (time.time() - self.last_updated) > self.stale_time:
            try:
                self.close()
            except e.ReportNotFound:
                pass

    def close(self):
        def get_report_path(report_id):
            return os.path.join(self.report_dir, report_id)

        report_filename = get_report_path(self.report_id)
        try:
            open(report_filename).close()
        except IOError:
            raise e.ReportNotFound

        dst_filename = report_file_name(archive_dir=self.archive_dir,
                                        report_details=self.report_details,
                                        report_id=self.report_id)
        shutil.move(report_filename, dst_filename)

        if not self.delayed_call.called:
            self.delayed_call.cancel()
        del self.reports[self.report_id]


def parseUpdateReportRequest(request, report_id=None):
    #db_report_id_regexp = re.compile("[a-zA-Z0-9]+$")

    # this is the regexp for the reports that include the timestamp
    report_id_regexp = re.compile("[a-zA-Z0-9_\-]+$")

    # XXX here we are actually parsing a json object that could be quite big.
    # If we want this to scale properly we only want to look at the test_id
    # field.
    # We are also keeping in memory multiple copies of the same object. A lot
    # of optimization can be done.
    parsed_request = json.loads(request)

    report_id = parsed_request.get('report_id', report_id)
    if not report_id:
        raise e.MissingField('report_id')

    if not re.match(report_id_regexp, report_id):
        raise e.InvalidRequestField('report_id')

    parsed_request['report_id'] = report_id
    return parsed_request


def validateHeader(header):
    version_string = re.compile("[0-9A-Za-z_\-\.]+$")
    name = re.compile("[a-zA-Z0-9_\- ]+$")
    probe_asn = re.compile("AS[0-9]+$")
    probe_cc = re.compile("[A-Z]{2}$")
    test_helper = re.compile("[A-Za-z0-9_\-]+$")

    expected_request = {
        'software_name': name,
        'software_version': version_string,
        'test_name': name,
        'test_version': version_string,
        'probe_asn': probe_asn,
        'probe_cc': probe_cc,
        'data_format_version': version_string
    }

    if not header.get('probe_asn'):
        header['probe_asn'] = 'AS0'

    if not header.get('probe_cc'):
        header['probe_cc'] = 'ZZ'

    if not header.get('start_time'):
        header['start_time'] = time.time()

    if not header.get('data_format_version'):
        header['data_format_version'] = '0.1.0'

    for k, regexp in expected_request.items():
        try:
            value_to_check = header[k]
        except KeyError:
            raise e.MissingField(k)

        log.debug("Matching %s with %s | %s" % (regexp, value_to_check, k))
        if re.match(regexp, str(value_to_check)):
            continue
        raise e.InvalidRequestField(k)

    try:
        requested_test_helper = header['test_helper']
        if not re.match(test_helper, str(requested_test_helper)):
            raise e.InvalidRequestField('test_helper')
    except KeyError:
        pass

    return header


def parseNewReportRequest(request):
    """
    Here we parse a new report request.
    """
    parsed_request = json.loads(request)
    parsed_request['format'] = parsed_request.get('format', 'yaml')

    parsed_request = validateHeader(parsed_request)

    return parsed_request

class ReportHandler(OONIBHandler):

    def initialize(self):
        self.archive_dir = config.main.archive_dir
        self.report_dir = config.main.report_dir
        self.reports = config.reports
        self.policy_file = config.main.policy_file
        self.helpers = config.helpers
        self.stale_time = config.main.stale_time


class UpdateReportMixin(object):
    def updateReport(self, report_id, parsed_request):

        log.msg("Got this request %s" % parsed_request)
        report_filename = os.path.join(self.report_dir,
                                       report_id)
        try:
            self.reports[report_id].refresh()
        except KeyError:
            raise e.OONIBError(404, "Report not found")

        content_format = parsed_request.get('format', 'yaml')
        if content_format == 'json':
            data = json_dumps(parsed_request['content'])
            data += "\n"
        elif content_format == 'yaml':
            data = parsed_request['content']
        else:
            raise e.InvalidFormatField
        try:
            with open(report_filename, 'a+') as fd:
                fd.write(data)
        except IOError:
            raise e.OONIBError(404, "Report not found")
        self.write({'status': 'success'})


class NewReportHandlerFile(ReportHandler, UpdateReportMixin):

    """
    Responsible for creating and updating reports by writing to flat file.
    """
    inputHashes = None

    def checkPolicy(self):
        policy = Policy()
        for input_hash in self.inputHashes:
            policy.validateInputHash(input_hash)
        policy.validateNettest(self.testName)

    def post(self):
        """
        Creates a new report with the input

        * Request

          {'software_name': 'XXX',
           'software_version': 'XXX',
           'test_name': 'XXX',
           'test_version': 'XXX',
           'probe_asn': 'XXX'
           'content': 'XXX'
           }

          Optional:
            'test_helper': 'XXX'
            'client_ip': 'XXX'

          (not implemented, nor in client, nor in backend)
          The idea behind these two fields is that it would be interesting to
          also collect how the request was observed from the collectors point
          of view.

          We use as a unique key the client_ip address and a time window. We
          then need to tell the test_helper that is selected the client_ip
          address and tell it to expect a connection from a probe in that time
          window.

          Once the test_helper sees a connection from that client_ip it will
          store for the testing session the data that it receives.
          When the probe completes the report (or the time window is over) the
          final report will include also the data collected from the
          collectors view point.

        * Response

          {
              'backend_version': 'XXX',
              'report_id': 'XXX',
              'supported_formats': ['yaml', 'json']
          }

        """
        # Note: the request is being validated inside of parseNewReportRequest.
        report_data = parseNewReportRequest(self.request.body)

        log.debug("Parsed this data %s" % report_data)

        self.testName = str(report_data['test_name'])
        self.testVersion = str(report_data['test_version'])

        if self.policy_file:
            try:
                self.inputHashes = report_data['input_hashes']
            except KeyError:
                raise e.InputHashNotProvided
            self.checkPolicy()

        data = None
        if report_data['format'] == 'yaml' and 'content' not in report_data:
            content = {
                'software_name': str(report_data['software_name']),
                'software_version': str(report_data['software_version']),
                'probe_asn': str(report_data['probe_asn']),
                'probe_cc': str(report_data['probe_cc']),
                'test_name': self.testName,
                'test_version': self.testVersion,
                'input_hashes': report_data.get('input_hashes', []),
                'start_time': report_data['start_time'],
                'data_format_version': str(report_data['data_format_version'])
            }
            data = "---\n" + yaml.dump(content) + "...\n"
        elif report_data['format'] == 'yaml' and 'content' in report_data:
            header = yaml.safe_load(report_data['content'])
            data = "---\n" + yaml.dump(validateHeader(header)) + "...\n"

        report_id = otime.timestamp() + '_' \
            + report_data.get('probe_asn', 'AS0') + '_' \
            + randomStr(50)

        # The report filename contains the timestamp of the report plus a
        # random nonce
        report_filename = os.path.join(self.report_dir, report_id)

        response = {
            'backend_version': config.backend_version,
            'report_id': report_id,
            'supported_formats': ['yaml', 'json']
        }

        requested_helper = report_data.get('test_helper')

        if requested_helper:
            try:
                response['test_helper_address'] = self.helpers[
                    requested_helper].address
            except KeyError:
                raise e.TestHelperNotFound

        self.reports[report_id] = Report(report_id=report_id,
            stale_time=self.stale_time,
            report_dir=self.report_dir,
            archive_dir=self.archive_dir,
            reports=self.reports,
            report_details=report_data
        )

        if data is not None:
            self.writeToReport(report_filename, data)
        else:
            open(report_filename, 'w+').close()

        self.write(response)

    def writeToReport(self, report_filename, data):
        with open(report_filename, 'w+') as fd:
            fdesc.setNonBlocking(fd.fileno())
            fdesc.writeToFD(fd.fileno(), data)

    def put(self):
        """
        Update an already existing report.

          {
           'report_id': 'XXX',
           'content': 'XXX'
          }
        """
        parsed_request = parseUpdateReportRequest(self.request.body)
        report_id = parsed_request['report_id']
        self.updateReport(report_id, parsed_request)


class UpdateReportHandlerFile(ReportHandler, UpdateReportMixin):
    def post(self, report_id):
        parsed_request = parseUpdateReportRequest(self.request.body, report_id)
        report_id = parsed_request['report_id']
        self.updateReport(report_id, parsed_request)


class CloseReportHandlerFile(ReportHandler):

    def get(self):
        pass

    def post(self, report_id):
        if report_id in self.reports:
            self.reports[report_id].close()
        else:
            raise e.ReportNotFound


class PCAPReportHandler(ReportHandler):

    def get(self):
        pass

    def post(self):
        pass
