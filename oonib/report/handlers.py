import time
import yaml
import json
import errno
import re

from twisted.python.filepath import FilePath, InsecurePath
from twisted.internet import reactor

from oonib import errors as e
from oonib.handlers import OONIBHandler
from oonib.policy.handlers import Policy

from datetime import datetime
from oonib import randomStr, otime, log, json_dumps
from oonib.config import config

METADATA_EXT = "-metadata.json"

def report_file_path(archive_dir, report_details,
                     report_id='no_report_id'):
    if report_details.get("start_time"):
        timestamp = datetime.fromtimestamp(report_details['start_time'])
    elif report_details.get("test_start_time"):
        timestamp = datetime.strptime(report_details['test_start_time'], "%Y-%m-%d %H:%M:%S")
    else:
        raise Exception("Could not find valid timestamp")
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

    dst_path = archive_dir.child(report_file_template.format(**keys))
    try:
        FilePath(dst_path.dirname()).makedirs()
    except OSError as e:
        if not e.errno == errno.EEXIST:
            raise
    return dst_path

def parseUpdateReportRequest(request, report_id=None):
    #db_report_id_regexp = re.compile("[a-zA-Z0-9]+$")

    # this is the regexp for the reports that include the timestamp
    report_id_regexp = re.compile(r"^[a-zA-Z0-9_\-]+$")

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
    # Version-number-regex context
    # ----------------------------
    #
    # We are updating our software to always use semver, but for historical
    # reasons there are also cases where we use '0.1', so better to be
    # very liberal an accept anything version-ish in here.
    #
    # Live regexp testing: https://regex101.com/r/zhnfFl/3
    #
    # See also: github.com/measurement-kit/measurement-kit/pull/1388
    version_string = re.compile(r"^[0-9A-Za-z_.+-]+$")

    name = re.compile(r"^[a-zA-Z0-9_\- ]+$")
    probe_asn = re.compile(r"^AS[0-9]+$")
    probe_cc = re.compile(r"^[A-Z]{2}$")
    test_helper = re.compile(r"^[A-Za-z0-9_\-]+$")

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

    if not header.get('test_start_time'):
        header['test_start_time'] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

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

    # This is to not accept new measurements coming from OONI Probe Android
    # 2.0.0, which was affected by bug:
    # https://github.com/ooni/probe-android/issues/188
    sw_name = header.get('software_name')
    sw_ver = header.get('software_version')
    if sw_name == 'ooniprobe-android' and (sw_ver == '2.0.0' or sw_ver.startswith('2.0.0-')):
        raise e.InvalidRequestField('software_version')

    return header


def parseNewReportRequest(request):
    """
    Here we parse a new report request.
    """
    parsed_request = json.loads(request)
    parsed_request['format'] = parsed_request.get('format', 'yaml')

    parsed_request = validateHeader(parsed_request)

    return parsed_request

def closeReport(report_id):
    report_dir = FilePath(config.main.report_dir)
    archive_dir = FilePath(config.main.archive_dir)
    report_path = report_dir.child(report_id)
    report_metadata_path = report_dir.child(report_id + METADATA_EXT)

    if not report_path.exists() or \
            not report_metadata_path.exists():
        raise e.ReportNotFound

    with report_metadata_path.open('r') as f:
        try:
            report_details = json.load(f)
        except ValueError:
            log.warn("Found corrupt metadata deleting %s and %s" %
                     (report_path.path, report_metadata_path.path))
            report_path.remove()
            report_metadata_path.remove()
            return

    dst_path = report_file_path(archive_dir,
                                report_details,
                                report_id)
    if report_path.getsize() > 0:
        report_path.moveTo(dst_path)
    else:
        # We currently just remove empty reports.
        # XXX Maybe in the future we want to keep track of how often this
        # happens.
        log.warn("Removing empty report %s" % report_path.path)
        report_path.remove()
    report_metadata_path.remove()

def checkForStaleReports( _time=time):
    delayed_call = reactor.callLater(config.main.stale_time,
                                     checkForStaleReports)
    report_dir = FilePath(config.main.report_dir)
    for report_metadata_path in \
            report_dir.globChildren("*"+METADATA_EXT):
        last_updated = _time.time() - \
                       report_metadata_path.getModificationTime()
        if last_updated > config.main.stale_time:
            report_id = report_metadata_path.basename().replace(
                METADATA_EXT, '')
            closeReport(report_id)
    return delayed_call


class ReportHandler(OONIBHandler):
    def initialize(self):
        self.archive_dir = FilePath(config.main.archive_dir)
        self.report_dir = FilePath(config.main.report_dir)

        self.policy_file = config.main.policy_file
        self.helpers = config.helpers

class UpdateReportMixin(object):
    def updateReport(self, report_id, parsed_request):

        log.debug("Got this request %s" % parsed_request)
        try:
            report_path = self.report_dir.child(report_id)
            report_metadata_path = self.report_dir.child(report_id +
                                                         METADATA_EXT)
        except InsecurePath:
            raise e.OONIBError(406, "Invalid report_id")

        content_format = parsed_request.get('format', 'yaml')
        if content_format == 'json':
            data = json_dumps(parsed_request['content'])
            data += "\n"
        elif content_format == 'yaml':
            data = parsed_request['content']
        else:
            raise e.InvalidFormatField

        if not report_path.exists() or \
                not report_metadata_path.exists():
            raise e.OONIBError(404, "Report not found")

        with report_path.open('a') as fd:
            fd.write(data)

        report_metadata_path.touch()

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
                'test_start_time': str(report_data['test_start_time']),
                'data_format_version': str(report_data.get('data_format_version', '0.1.0'))
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
        report_path = self.report_dir.child(report_id)
        # We use this file to store the metadata associated with the report
        # submission.
        report_metadata_path = self.report_dir.child(report_id + METADATA_EXT)

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

        with report_metadata_path.open('w') as f:
            f.write(json_dumps(report_data))
            f.write("\n")

        report_path.touch()
        if data is not None:
            with report_path.open('w') as f:
                f.write(data)

        self.write(response)

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
        closeReport(report_id)

class PCAPReportHandler(ReportHandler):

    def get(self):
        pass

    def post(self):
        pass
