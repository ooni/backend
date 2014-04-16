import random
import string
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
from oonib import randomStr, otime, log
from oonib.config import config

class MissingField(Exception):
    pass

class InvalidRequestField(Exception):
    pass

class Report(object):
    def __init__(self, report_id):
        self.report_id = report_id
        self.delayed_call = None

        self.refresh()
    
    def refresh(self):
        self.last_updated = time.time()
        if self.delayed_call:
            self.delayed_call.cancel()
        self.delayed_call = reactor.callLater(config.main.stale_time, self.stale_check)

    def stale_check(self):
        if (time.time() - self.last_updated) > config.main.stale_time:
            try:
                self.close()
            except ReportNotFound:
                pass

    def close(self):
        def get_report_path(report_id):
            return os.path.join(config.main.report_dir, report_id)

        report_filename = get_report_path(self.report_id)
        try:
            with open(report_filename) as fd:
                g = yaml.safe_load_all(fd)
                report_details = g.next()
        except IOError:
            raise ReportNotFound

        timestamp = otime.timestamp(datetime.fromtimestamp(report_details['start_time']))
        dst_filename = '{test_name}-{timestamp}-{probe_asn}-probe.yamloo'.format(
                timestamp=timestamp,
                **report_details)

        dst_path = os.path.join(config.main.archive_dir,
                                report_details['probe_cc'])

        if not os.path.isdir(dst_path):
            os.mkdir(dst_path)

        dst_path = os.path.join(dst_path, dst_filename)
        os.rename(report_filename, dst_path)

        del config.reports[self.report_id]

def parseUpdateReportRequest(request):
    #db_report_id_regexp = re.compile("[a-zA-Z0-9]+$")

    # this is the regexp for the reports that include the timestamp
    report_id_regexp = re.compile("[a-zA-Z0-9_\-]+$")

    # XXX here we are actually parsing a json object that could be quite big.
    # If we want this to scale properly we only want to look at the test_id
    # field.
    # We are also keeping in memory multiple copies of the same object. A lot
    # of optimization can be done.
    parsed_request = json.loads(request)
    try:
        report_id = parsed_request['report_id']
    except KeyError:
        raise MissingField('report_id')

    if not re.match(report_id_regexp, report_id):
        raise InvalidRequestField('report_id')

    return parsed_request

def parseNewReportRequest(request):
    """
    Here we parse a new report request.
    """
    version_string = re.compile("[0-9A-Za-z_\-\.]+$")
    name = re.compile("[a-zA-Z0-9_\- ]+$")
    probe_asn = re.compile("AS[0-9]+$")
    test_helper = re.compile("[A-Za-z0-9_\-]+$")

    expected_request = {
     'software_name': name,
     'software_version': version_string,
     'test_name': name,
     'test_version': version_string,
     'probe_asn': probe_asn
    }

    parsed_request = json.loads(request)
    if 'probe_asn' not in parsed_request or not parsed_request['probe_asn']:
        parsed_request['probe_asn'] = 'AS0'

    for k, regexp in expected_request.items():
        try:
            value_to_check = parsed_request[k]
        except KeyError:
            raise MissingField(k)

        print "Matching %s with %s | %s" % (regexp, value_to_check, k)
        if re.match(regexp, str(value_to_check)):
            continue
        else:
            raise InvalidRequestField(k)
    
    try:
        requested_test_helper = parsed_request['test_helper']
        if not re.match(test_helper, str(requested_test_helper)):
            raise InvalidRequestField('test_helper')
    except KeyError:
        pass

    return parsed_request

class InvalidReportHeader(Exception):
    pass

class MissingReportHeaderKey(InvalidReportHeader):
    pass

def validate_report_header(report_header):
    required_keys = ['probe_asn', 'probe_cc', 'probe_ip', 'software_name',
            'software_version', 'test_name', 'test_version']
    for key in required_keys:
        if key not in report_header:
            raise MissingReportHeaderKey(key)

    if report_header['probe_asn'] is None:
        report_header['probe_asn'] = 'AS0'

    if not re.match('AS[0-9]+$', report_header['probe_asn']):
        raise InvalidReportHeader('probe_asn')

    # If no country is known, set it to be ZZ (user assigned value in ISO 3166)
    if report_header['probe_cc'] is None:
        report_header['probe_cc'] = 'ZZ'

    if not re.match('[a-zA-Z]{2}$', report_header['probe_cc']):
        raise InvalidReportHeader('probe_cc')

    if not re.match('[a-z_\-]+$', report_header['test_name']):
        raise InvalidReportHeader('test_name')


    if not re.match('([0-9]+\.)+[0-9]+$', report_header['test_version']):
        raise InvalidReportHeader('test_version')

    return report_header

class UpdateReportMixin(object):
    def updateReport(self, report_id, parsed_request):

        log.debug("Got this request %s" % parsed_request)
        report_filename = os.path.join(config.main.report_dir,
                report_id)
        
        config.reports[report_id].refresh()

        try:
            with open(report_filename, 'a+') as fd:
                fdesc.setNonBlocking(fd.fileno())
                fdesc.writeToFD(fd.fileno(), parsed_request['content'])
        except IOError as exc:
            e.OONIBError(404, "Report not found")
        self.write({})

class NewReportHandlerFile(OONIBHandler, UpdateReportMixin):
    """
    Responsible for creating and updating reports by writing to flat file.
    """

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

          {'backend_version': 'XXX', 'report_id': 'XXX'}

        """
        # XXX here we should validate and sanitize the request
        try:
            report_data = parseNewReportRequest(self.request.body)
        except InvalidRequestField as exc:
            raise e.InvalidRequestField(exc)
        except MissingField as exc:
            raise e.MissingRequestField(exc)

        log.debug("Parsed this data %s" % report_data)

        software_name = str(report_data['software_name'])
        software_version = str(report_data['software_version'])
        
        probe_asn = str(report_data['probe_asn'])
        probe_cc = str(report_data.get('probe_cc', 'ZZ'))

        self.testName = str(report_data['test_name'])
        self.testVersion = str(report_data['test_version'])
       
        if config.main.policy_file:
            try:
                self.inputHashes = report_data['input_hashes']
            except KeyError:
                raise e.InputHashNotProvided
            self.checkPolicy()
        
        if 'content' in report_data:
            content = yaml.safe_load(report_data['content'])
            try:
                report_header = validate_report_header(content)

            except MissingReportHeaderKey, key:
                raise e.MissingReportHeaderKey(key)

            except InvalidReportHeader, key:
                raise e.InvalidReportHeader(key)
        else:
            content = {
                'software_name': software_name,
                'software_version': software_version,
                'probe_asn': probe_asn,
                'probe_cc': probe_cc,
                'test_name': self.testName,
                'test_version': self.testVersion,
                'input_hashes': self.inputHashes,
                'start_time': time.time()
            }

        content['backend_version'] = config.backend_version

        report_header = yaml.dump(content)
        content = "---\n" + report_header + '...\n'

        if not probe_asn:
            probe_asn = "AS0"

        report_id = otime.timestamp() + '_' \
                + probe_asn + '_' \
                + randomStr(50)

        # The report filename contains the timestamp of the report plus a
        # random nonce
        report_filename = os.path.join(config.main.report_dir, report_id)

        response = {
            'backend_version': config.backend_version,
            'report_id': report_id
        }
        
        requested_helper = report_data.get('test_helper')

        if requested_helper:
            try:
                response['test_helper_address'] = config.helpers[requested_helper].address
            except KeyError:
                raise e.TestHelperNotFound
        
        config.reports[report_id] = Report(report_id)

        self.writeToReport(report_filename, content)

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

class UpdateReportHandlerFile(OONIBHandler, UpdateReportMixin):
    def post(self, report_id):
        try:
            parsed_request = json.loads(self.request.body)
        except ValueError:
            raise e.InvalidRequest
        self.updateReport(report_id, parsed_request)

class ReportNotFound(Exception):
    pass

class CloseReportHandlerFile(OONIBHandler):
    def get(self):
        pass

    def post(self, report_id):
        if report_id in config.reports:
            config.reports[report_id].close()
        else:
            raise e.ReportNotFound

class PCAPReportHandler(OONIBHandler):
    def get(self):
        pass

    def post(self):
        pass
