import traceback
import hashlib
import logging
import string
import random
import uuid
import re
import os

from base64 import b64encode
from datetime import datetime

import luigi
import luigi.postgres

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

try:
    from ujson import loads as json_loads
    from ujson import dumps as json_dumps
except ImportError:
    logger.warning("ujson is not available, "
                   "performance will be seriously degraded.")
    from json import loads as json_loads
    from json import dumps as json_dumps

import yaml
try:
    from yaml import CLoader as Loader
except ImportError:
    logger.warning("YAML is not compiled with c bindings, "
                   "performance will be seriously degraded.")
    from yaml import Loader as Loader

config = luigi.configuration.get_config()

test_name_mappings = {
    "http_host": "http_host",
    "HTTP Host": "http_host",

    "http_requests_test": "http_requests",
    "http_requests":"http_requests",
    "HTTP Requests Test": "http_requests",

    "bridge_reachability": "bridge_reachability",
    "bridgereachability": "bridge_reachability",

    "TCP Connect": "tcp_connect",
    "tcp_connect": "tcp_connect",

    "DNS tamper": "dns_consistency",
    "dnstamper": "dns_consistency",
    "dns_consistency": "dns_consistency",

    "HTTP Invalid Request Line": "http_invalid_request_line",
    "http_invalid_request_line": "http_invalid_request_line",

    "http_header_field_manipulation": "http_header_field_manipulation",
    "HTTP Header Field Manipulation": "http_header_field_manipulation",

    "Multi Protocol Traceroute Test": "multi_protocol_traceroute",
    "multi_protocol_traceroute_test": "multi_protocol_traceroute",
    "multi_protocol_traceroute": "multi_protocol_traceroute",
    "traceroute": "multi_protocol_traceroute",

    "parasitic_traceroute_test": "parasitic_traceroute",
    "parasitic_tcp_traceroute_test": "parasitic_traceroute",

    "tls-handshake": "tls_handshake",
    "tls_handshake": "tls_handshake",

    "dns_injection": "dns_injection",

    "captivep": "captive_portal",
    "captiveportal": "captive_portal",

    "HTTPFilteringBypass": "http_filtering_bypass",
    "httpfilteringbypass": "http_filtering_bypass",

    "HTTPTrix": "http_trix",
    "httptrix": "http_trix",
    "http_test": "http_test",
    "http_url_list": "http_url_list",
    "dns_spoof": "dns_spoof",
    "netalyzrwrapper": "netalyzr_wrapper",


    "this_test_is_nameless": "this_test_is_nameless",

    "test_get_random_capitalization": "http_header_field_manipulation",
    "test_put_random_capitalization": "http_header_field_manipulation",
    "test_post_random_capitalization": "http_header_field_manipulation",

    "test_random_big_request_method": "http_invalid_request_line",
    "test_random_invalid_field_count": "http_invalid_request_line",

    "summary": "invalid",
    "test_get": "invalid",
    "test_post": "invalid",
    "test_put": "invalid",
    "test_send_host_header": "invalid"
}

schema = [
    'id',
    'input',
    'report_id',
    'report_filename',
    'options',
    'probe_cc',
    'probe_asn',
    'probe_ip',
    'data_format_version',
    'test_name',
    'test_start_time',
    'test_runtime',
    'test_helpers',
    'software_name',
    'software_version',
    'bucket_date',
    'test_keys'
]

test_categories = {
    'dnst': {
        'dns_consistency',
        'dns_injection',
        'captive_portal',
    },
    'process': {
        'lantern',
        'psiphon',
    },
    'httpt': {
        'http_requests',
        'meek_fronted_requests',
        'domclass_collector',
        'http_keyword_filtering',
        'http_uk_mobile_networks',
        'http_header_field_manipulation',
        'http_url_list',
        'http_host',
        'squid',
        'captive_portal',
        'psiphon',
    },
    'scapyt': {
        'chinatrigger',
        'keyword_filtering',
        'parasitic_traceroute',
        'traceroute',
        'dns_spoof',
    },
    'tcpt': {
        'http_filtering_bypass',
        'http_invalid_request_line',
        'http_trix',
    }
}

def binary_to_base64_dict(data):
    return {
        "data": b64encode(data),
        "format": "base64"
    }

def get_luigi_target(path):
    try:
        from urlparse import urlparse
    # Python3 compatibility
    except ImportError:
        from urllib.parse import urlpase
    from luigi.s3 import S3Target
    from luigi.contrib.ssh import RemoteTarget
    from luigi.file import LocalTarget
    from luigi.format import GzipFormat

    file_format = None
    if path.endswith(".gz"):
        file_format = GzipFormat()
    if path.startswith("s3n://"):
        return S3Target(path, format=file_format)
    elif path.startswith("ssh://"):
        ssh_key_file = config.get("ssh", "ssh-key-file", None)
        no_host_key_check = config.get("ssh", "no-host-key-check", None)
        p = urlparse(path)
        return RemoteTarget(p.path, p.hostname, format=format,
                            username=p.username,
                            sshpass=p.password,
                            key_file=ssh_key_file,
                            no_host_key_check=no_host_key_check)
    return LocalTarget(path, format=file_format)

class ReadReport(luigi.ExternalTask):
    report_path = luigi.Parameter()
    def output(self):
        return get_luigi_target(self.report_path)

class NormaliseReport(luigi.Task):
    """"This task is responsible for reading the RAW report that is
    in either YAML or JSON format from the specified path, transforming it into
    JSON, adding all the missing keys and normalising the values of the ones
    present.

    report_path:
        The file path to the specified report. It is expected that the
        report_path follows the following format:
            s3n:// | ssh:// [[USER]:[PASS]] @ [HOST] / OONI_PRIVATE_DIR
                                                    / { bucket_date } /
            { test_name }-{ timestamp }-{ asn }-{ probe_cc }-probe-v2.yaml

            Where bucket_date is the date of the bucket where the report is
            in expressed as %Y-%M-%d and timestamp is the timestamp of when
            the report was generated expressed as %Y%M%dT%H%m%s.
    """
    report_path = luigi.Parameter()

    def requires(self):
        return ReadReport(self.report_path)

    @staticmethod
    def _normalise_httpt(entry):
        def _normalise_body(body):
            if body is None:
                return body
            try:
                body = body.replace("\0", "")
                body = unicode(body)
            except UnicodeDecodeError:
                body = binary_to_base64_dict(body)
            return body

        def _normalise_headers(headers):
            normalised_headers = {}
            for name, values in headers:
                for v in values:
                    normalised_headers[name] = v
            return normalised_headers

        experiment_requests = []
        control_requests = []

        for session in entry['test_keys']['requests']:
            if isinstance(session.get('response'), dict):
                session['response']['body'] = _normalise_body(session['response']['body'])
                session['response']['headers'] = _normalise_headers(session['response']['headers'])
            else:
                session['response'] = {'body': None, 'headers': {}}
            is_tor = False
            if session['request']['url'].startswith('shttp'):
                session['request']['url'] = session['request']['url'].replace('shttp://', 'http://')
                is_tor = True
            elif session['request'].get('tor') is True:
                is_tor = True
            elif session['request'].get('tor') in [False, None, {'is_tor': False}]:
                is_tor = True
            elif session['request'].get('tor', {}).get('is_tor') is True:
                is_tor = True
            else:
                logger.error("Could not detect tor or not tor status")
                logger.debug(session)
            session['request']['tor'] = {'is_tor': is_tor}
            session['response_length'] = None
            for k, v in session['response']['headers'].items():
                if k.lower() == 'content-length':
                    session['response_length'] = v
            if is_tor is True:
                control_requests.append(session)
            else:
                experiment_requests.append(session)
        entry['test_keys']['requests'] = []
        try:
            entry['test_keys']['requests'].append(experiment_requests.pop(0))
        except IndexError:
            pass
        try:
            entry['test_keys']['requests'].append(control_requests.pop(0))
        except IndexError:
            pass
        entry['test_keys']['requests'] += experiment_requests
        entry['test_keys']['requests'] += control_requests
        return entry

    @staticmethod
    def _normalise_dnst(entry):
        return entry

    @staticmethod
    def _normalise_scapyt(entry):
        answered_packets = []
        sent_packets = []
        for pkt in entry['test_keys'].get('answered_packets', []):
            try:
                sanitised_packet = {
                    "raw_packet": binary_to_base64_dict(pkt[0]['raw_packet']),
                    "summary": pkt[0]['summary']
                }
                answered_packets.append(sanitised_packet)
            except IndexError:
                logger.error("Failed to find the index of the packet")
                continue
        for pkt in entry['test_keys'].get('sent_packets', []):
            try:
                sanitised_packet = {
                    "raw_packet": binary_to_base64_dict(pkt[0]['raw_packet']),
                    "summary": pkt[0]['summary']
                }
                sent_packets.append(sanitised_packet)
            except IndexError:
                logger.error("Failed to find the index of the packet")
                continue
        entry['test_keys']['sent_packets'] = sent_packets
        entry['test_keys']['answered_packets'] = answered_packets
        return entry

    @staticmethod
    def _normalise_tcpt(entry):
        return entry

    @staticmethod
    def _normalise_process(entry):
        return entry

    def _normalise_entry(self, entry):
        bucket_date = os.path.basename(os.path.dirname(self.report_path))

        if isinstance(entry.get('report'), dict):
            entry.update(entry.pop('report'))

        test_name = entry.get('test_name', 'invalid')
        test_name = test_name_mappings.get(test_name, 'invalid')
        entry['test_name'] = test_name

        entry['bucket_date'] = bucket_date

        entry['test_start_time'] = datetime.fromtimestamp(entry.get('start_time',
                                        0)).strftime("%Y-%m-%d %H:%M:%S")

        entry['id'] = entry.get('id', str(uuid.uuid4()))
        entry['report_filename'] = os.path.join(bucket_date,
                                    os.path.basename(self.output().path))
        entry['data_format_version'] = '0.2.0'

        for key in schema:
            entry[key] = entry.get(key, None)

        if entry['test_keys'] is None:
            entry['test_keys'] = {}
        for test_key in set(entry.keys()) - set(schema):
            entry['test_keys'][test_key] = entry.pop(test_key)

        if test_name in test_categories['httpt']:
            entry = self._normalise_httpt(entry)
        if test_name in test_categories['dnst']:
            entry = self._normalise_dnst(entry)
        if test_name in test_categories['tcpt']:
            entry = self._normalise_tcpt(entry)
        if test_name in test_categories['process']:
            entry = self._normalise_processt(entry)
        if test_name in test_categories['scapyt']:
            entry = self._normalise_scapyt(entry)
        return entry

    def _yaml_report_iterator(self, fobj):
        report = yaml.load_all(fobj, Loader=Loader)
        header = report.next()
        start_time = datetime.fromtimestamp(header.get('start_time', 0))
        report_id = start_time.strftime("%Y%m%dT%H%M%SZ_")
        report_id += ''.join(random.choice(string.ascii_letters)
                             for x in range(50))
        header['report_id'] = header.get('report_id', report_id)
        for entry in report:
            entry.update(header)
            yield entry

    def _json_report_iterator(self, fobj):
        for line in fobj:
            yield json_loads(line.strip())

    def _report_iterator(self, fobj):
        if self.report_path.endswith(".yamloo") or \
                self.report_path.endswith(".yaml"):
            return self._yaml_report_iterator(fobj)
        elif self.report_path.endswith(".json"):
            return self._json_report_iterator(fobj)

    def run(self):
        out_file = self.output().open('w')
        with self.input().open('r') as fobj:
            for entry in self._report_iterator(fobj):
                try:
                    normalised_entry = self._normalise_entry(entry)
                except Exception:
                    logger.error("%s: error in normalising entry" % self.report_path)
                    logger.error(traceback.format_exc())
                    logger.debug(entry)
                    continue
                try:
                    out_file.write(json_dumps(normalised_entry))
                except Exception:
                    logger.error("%s: error in serialising entry" % self.report_path)
                    logger.error(traceback.format_exc())
                    logger.debug(entry)
        out_file.close()

    def _get_dst_path(self):
        ooni_private_dir = config.get("ooni", "private-dir")
        bucket_date = os.path.basename(os.path.dirname(self.report_path))
        filename = os.path.splitext(os.path.basename(self.report_path))[0] + ".json"
        return os.path.join(ooni_private_dir, "reports-raw",
                            "normalised", bucket_date, filename)

    def output(self):
        return get_luigi_target(self._get_dst_path())

class SanitiseReport(luigi.Task):
    report_path = luigi.Parameter()

    def requires(self):
        return NormaliseReport(self.report_path)

    def _get_dst_path(self):
        ooni_public_dir = config.get("ooni", "public-dir")
        bucket_date = os.path.basename(os.path.dirname(self.report_path))
        filename = os.path.splitext(os.path.basename(self.report_path))[0] + ".json"
        return os.path.join(ooni_public_dir,
                            "sanitised", bucket_date, filename)

    def output(self):
        return get_luigi_target(self._get_dst_path())

    @staticmethod
    def _sanitise_bridge_reachability(entry, bridge_db):
        entry['test_name'] = 'bridge_reachability'
        if not entry.get('bridge_address'):
            entry['bridge_address'] = entry['input']

        if entry['bridge_address'] and \
                entry['bridge_address'].strip() in bridge_db:
            b = bridge_db[entry['bridge_address'].strip()]
            entry['distributor'] = b['distributor']
            entry['transport'] = b['transport']
            fingerprint = b['fingerprint'].decode('hex')
            hashed_fingerprint = hashlib.sha1(fingerprint).hexdigest()
            entry['input'] = hashed_fingerprint
            entry['bridge_address'] = None
            regexp = ("(Learned fingerprint ([A-Z0-9]+)"
                    "\s+for bridge (([0-9]+\.){3}[0-9]+\:\d+))|"
                    "((new bridge descriptor .+?\s+"
                    "at (([0-9]+\.){3}[0-9]+)))")
            if entry.get('tor_log'):
                entry['tor_log'] = re.sub(regexp, "[REDACTED]", entry['tor_log'])
            else:
                entry['tor_log'] = None
        else:
            entry['distributor'] = None
            hashed_fingerprint = None
        entry['bridge_hashed_fingerprint'] = hashed_fingerprint
        return entry

    @staticmethod
    def _sanitise_tcp_connect(entry, bridge_db):
        if entry['input'] and entry['input'].strip() in bridge_db.keys():
            b = bridge_db[entry['input'].strip()]
            fingerprint = b['fingerprint'].decode('hex')
            hashed_fingerprint = hashlib.sha1(fingerprint).hexdigest()
            entry['bridge_hashed_fingerprint'] = hashed_fingerprint
            entry['input'] = hashed_fingerprint
            return entry
        return entry

    def run(self):
        bridge_db_path = config.get("ooni", "bridge-db-path")
        bridge_db = json_loads(open(bridge_db_path).read())
        out_file = self.output().open('w')
        with self.input().open('r') as fobj:
            for line in fobj:
                entry = json_loads(line.strip())
                if entry['test_name']  == 'tcp_connect':
                    entry = self._sanitise_tcp_connect(entry, bridge_db)
                elif entry['test_name'] == 'bridge_reachability':
                    entry = self._sanitise_bridge_reachability(entry, bridge_db)
                out_file.write(json_dumps(entry))
        out_file.close()

class InsertMeasurementsIntoPostgres(luigi.postgres.CopyToTable):
    host = config.get("postgres", "host")
    database = config.get("postgres", "database")
    user = config.get("postgres", "user")
    password = config.get("postgres", "password")
    table = config.get("postgres", "metrics-table")

    report_path = luigi.Parameter()

    columns = [
        ('id', 'UUID PRIMARY KEY'),
        ('input', 'TEXT'),
        ('report_id', 'TEXT'),
        ('report_filename', 'TEXT'),
        ('options', 'JSONB'),
        ('probe_cc', 'TEXT'),
        ('probe_asn', 'TEXT'),
        ('probe_ip', 'TEXT'),
        ('data_format_version', 'TEXT'),
        ('test_name', 'TEXT'),
        ('test_start_time', 'TIMESTAMP'),
        ('test_runtime', 'REAL'),
        ('test_helpers', 'JSONB'),
        ('test_keys', 'JSONB'),
        ('software_name', 'TEXT'),
        ('software_version', 'TEXT'),
        ('test_version', 'TEXT'),
        ('bucket_date', 'DATE')
    ]

    def requires(self):
        return SanitiseReport(self.report_path)

    def _format_record(self, line, idx):
        try:
            record = json_loads(line)
        except Exception:
            logger.error("%s:%s error in parsing JSON" % (self.report_path, idx))
            logger.error(traceback.format_exc())

        row = []
        for key, data_type in self.columns:
            try:
                value = record[key]
            except KeyError:
                logger.error("%s:%s could not find key" % (self.report_path, idx, key))
                logger.debug(record)
                raise Exception("Could not find key in report")
            row.append(value)
        return row

    def rows(self):
        with self.input().open('r') as fobj:
            for idx, line in enumerate(fobj):
                yield self._format_record(line.strip(), idx)

class ListReportsAndRun(luigi.WrapperTask):
    date_interval = luigi.DateIntervalParameter()
    task = luigi.Parameter(default="InsertMeasurementsIntoPostgres")

    @staticmethod
    def _list_reports_in_bucket(date):
        ooni_private_dir = config.get("ooni", "raw-reports-dir")
        bucket_path = os.path.join(ooni_private_dir, date.strftime("%Y-%m-%d"))
        return get_luigi_target(bucket_path).fs.listdir(bucket_path)

    def requires(self):
        try:
            task_factory = globals()[self.task]
        except AttributeError:
            raise Exception("Could not located task '%s'" % self.task)
        task_list = []
        for date in self.date_interval:
            for report_path in self._list_reports_in_bucket(date):
                task_list.append(task_factory(report_path))
        return task_list
