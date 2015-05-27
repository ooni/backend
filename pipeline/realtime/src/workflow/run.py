import os
import sys
import time
import json
import shutil
import traceback
from datetime import datetime
from StringIO import StringIO

from boto.s3.connection import S3Connection

sys.path.append(os.path.join(os.path.dirname(__file__), '../'))
from workflow.binario import Emitter, Pipe
from helpers.settings import config
from helpers.util import json_dumps

from helpers.s3 import S3Downloader
from helpers.report import Report


class TimedStringIO(StringIO):
    def __init__(self, timeout=10, *args, **kw):
        self.timeout = timeout
        self._last_write = time.time()
        StringIO.__init__(self, *args, **kw)

    @property
    def timed_out(self):
        if time.time() - self._last_write > self.timeout:
            return True
        return False

    def write(self, s):
        self._last_write = time.time()
        return StringIO.write(self, s)


class BucketManager(object):
    max_bucket_size = 1024 * 1024 * 64
    output_dir = '/data1/reports/'

    def __init__(self, suffix, timeout=30):
        self.suffix = suffix
        self.timeout = timeout

        self.date_buckets = {}
        self.report_buckets = {}
        self.message_queue_bucket = {
            'reports': {},
            'dates': {}
        }

    def check_timeouts(self):
        for date, string in self.date_buckets.items():
            if string.timed_out:
                self.flush_date_bucket(date)

    def flush_date_bucket(self, date):
        print("Flushing date bucket %s" % date)
        self.date_buckets[date].seek(0)
        base_name = os.path.join(self.output_dir, date + self.suffix)
        # Currently disabled generating new names for entries
        # idx = 0
        # while os.path.exists("%s-%s" % (base_name, idx)):
        #     idx += 1
        # dst_file = "%s-%s" % (base_name, idx)
        with open(base_name, 'a+') as out_file:
            shutil.copyfileobj(self.date_buckets[date], out_file)
        # Delete the date in this key
        del self.date_buckets[date]

    def flush_all(self):
        for date, _ in self.date_buckets.items():
            self.flush_date_bucket(date)

    def add_message(self, report_id, data):
        if data[0] in ("e", "h"):
            self.add_to_report_bucket(report_id, data[1:])
        elif data[0] == "f":
            report = json.loads(data[1:])
            self.add_to_report_bucket(report_id, data[1:])
            self.add_to_date_bucket(report)
        elif data[0] == "d":
            self.flush_all()

    def add_to_report_bucket(self, report_id, report_data):
        if not self.report_buckets.get(report_id):
            self.report_buckets[report_id] = TimedStringIO(self.timeout)
        self.report_buckets[report_id].write(report_data)
        self.report_buckets[report_id].write("\n")

    def add_to_date_bucket(self, report):
        report_date = datetime.fromtimestamp(
            report['start_time']).strftime('%Y-%m-%d')
        report_id = report['report_id']
        if not self.date_buckets.get(report_date):
            self.date_buckets[report_date] = TimedStringIO(self.timeout)

        # Move the reports from the report bucket into the date bucket
        self.report_buckets[report_id].seek(0)
        self.date_buckets[report_date].write(
            self.report_buckets[report_id].read()
        )
        del self.report_buckets[report_id]

        # If we have reached the acceptable block size we can flush to disk
        if self.date_buckets[report_date].len > self.max_bucket_size:
            self.flush_date_bucket(report_date)
        else:
            print("Date bucket is not yet full current size: %s" %
                  self.date_buckets[report_date].len)


class S3AddressEmitter(Emitter):
    def emit(self):
        folder = 'reports'
        access_key_id = config["aws"]["access-key-id"]
        secret_access_key = config["aws"]["secret-access-key"]
        bucket_name = config["aws"]["s3-bucket-name"]

        s3_connection = S3Connection(access_key_id, secret_access_key)
        bucket = s3_connection.get_bucket(bucket_name)

        for key in bucket.list(folder):
            report_uri = "s3://%s/%s" % (bucket_name, key.name)
            self.log("Emitting %s" % report_uri)
            yield report_uri


class ReportParsePipe(Pipe):
    def initialize(self):
        access_key_id = config["aws"]["access-key-id"]
        secret_access_key = config["aws"]["secret-access-key"]
        bucket_name = config["aws"]["s3-bucket-name"]
        self.s3_downloader = S3Downloader(access_key_id, secret_access_key,
                                          bucket_name)

    def process_report(self, in_file):
        report = Report(in_file)
        for sanitised_entry, raw_entry in report.entries():
            report_id = sanitised_entry["report_id"]
            record_type = sanitised_entry["record_type"]
            s_report_data = json_dumps(sanitised_entry)
            r_report_data = json_dumps(raw_entry)
            yield report_id, record_type, s_report_data, r_report_data
        in_file.close()
        os.remove(in_file.name)

    def process(self, report_uri):
        self.log("Got %s" % report_uri)
        if report_uri.startswith('s3'):
            in_file = self.s3_downloader.download(report_uri)
        else:
            raise Exception("Unsupported URI")

        try:
            for r_id, r_type, s_d, r_d in self.process_report(in_file):
                yield r_id, r_type, s_d, r_d
        except Exception as exc:
            print(traceback.format_exc())
            raise exc


class SerializePipe(Pipe):
    def process(self, data):
        report_id, record_type, s_payload, r_payload = data
        self.log('Processing: %s' % report_id)
        s_payload = str(s_payload)
        r_payload = str(r_payload)
        report_id = str(report_id)
        if record_type == "entry":
            s_payload = str("e" + s_payload)
            r_payload = str("e" + r_payload)
        elif record_type == "header":
            s_payload = str("h" + s_payload)
            r_payload = str("h" + r_payload)
        elif record_type == "footer":
            s_payload = str("f" + s_payload)
            r_payload = str("f" + r_payload)
        yield report_id, s_payload, r_payload


class BucketPipe(Pipe):
    def initialize(self):
        self.last_check = time.time()
        self.timeout = 30
        self.raw_bucket_manager = BucketManager(".raw", self.timeout)
        self.sanitised_bucket_manager = BucketManager(".sanitised",
                                                      self.timeout)

    def process(self, data):
        report_id = data[0]
        s_payload, r_payload = data[1:]
        self.log("Bucketing %s" % report_id)
        self.sanitised_bucket_manager.add_message(report_id, s_payload)
        self.raw_bucket_manager.add_message(report_id, r_payload)
        if time.time() - self.last_check > self.timeout:
            self.sanitised_bucket_manager.check_timeouts()
            self.raw_bucket_manager.check_timeouts()
            self.last_check = time.time()

s3_address_emitter = S3AddressEmitter(1)
report_parse_pipe = ReportParsePipe(24)
serialize_pipe = SerializePipe(12)
bucket_pipe = BucketPipe(1)

s3_address_emitter.into(report_parse_pipe)
report_parse_pipe.into(serialize_pipe)
serialize_pipe.into(bucket_pipe)

s3_address_emitter.start()
