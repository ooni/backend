import re
import os
import json
import random
import string
import shutil
import base64
import hashlib
import traceback
from datetime import datetime

import yaml

import luigi
import luigi.worker
import luigi.hdfs
from luigi.task import ExternalTask
from luigi.format import GzipFormat
from luigi.s3 import S3Target
from luigi.configuration import get_config
# from luigi.contrib.spark import SparkSubmitTask, PySparkTask
import sanitise

def list_raw_reports():
    config = get_config()
    from boto.s3.connection import S3Connection

    AWS_ACCESS_KEY_ID = config.get('aws', 'access-key-id')
    AWS_SECRET_ACCESS_KEY = config.get('aws', 'secret-access-key')

    S3_BUCKET_NAME = config.get('aws', 's3-bucket-name')

    con = S3Connection(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    bucket = con.get_bucket(S3_BUCKET_NAME)
    keys = bucket.list('reports')
    for key in keys:
        yield (S3_BUCKET_NAME, key.name)


encode_basestring_ascii_orig = json.encoder.encode_basestring_ascii
def encode_basestring_ascii(o):
    try:
        return encode_basestring_ascii_orig(o)
    except UnicodeDecodeError:
        return json.dumps({"base64": base64.b64encode(o)})
json.encoder.encode_basestring_ascii = encode_basestring_ascii

def json_default(o):
    if isinstance(o, set):
        return list(o)
    return json.JSONEncoder.default(o)

def json_dump(data, fh):
    encoder = json.JSONEncoder(ensure_ascii=True, default=json_default)
    for chunk in encoder.iterencode(data):
        fh.write(chunk)


class S3GzipTask(ExternalTask):
    path = luigi.Parameter()

    def output(self):
        return S3Target(self.path, format=GzipFormat())


class ReportProcessor(object):
    def __init__(self, in_file, raw_file, sanitised_file, log_filename=None):
        self.in_file = in_file
        self.raw_file = raw_file
        self.sanitised_file = sanitised_file
        if not log_filename:
            log_filename = datetime.now().strftime("%Y-%m-%dT%H%M%S.imported")
        self.log_filename = log_filename

    def failure(self, traceback, state):
        message = {
            "traceback": traceback,
            "state": state
        }
        print "Fail in %s" % state
        print traceback
        with open(self.log_filename + ".err", 'a') as fh:
            self.write_json_entry(message, fh)

    def open(self):
        self.in_fh = self.in_file.open("r")
        self.raw_fh = self.raw_file.open("a")
        self.sanitised_fh = self.sanitised_file.open("a")

    def done(self):
        with open(self.log_filename, 'a') as fh:
            fh.write(self.in_file.path + "\n")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, value, traceback):
        if exc_type:
            self.failure(exc_type, value, traceback, "exit")
        self.in_fh.close()
        self.raw_fh.close()
        self.sanitised_fh.close()

    def write_json_entry(self, entry, fh):
        json_dump(entry, fh)
        fh.write("\n")

    def sanitise_header(self, entry):
        return entry

    def process_header(self, report):
        self.header = report.next()

        date = datetime.fromtimestamp(self.header["start_time"])
        date = date.strftime("%Y-%m-%d")
        if not self.header.get("report_id"):
            nonce = ''.join(random.choice(string.ascii_lowercase)
                            for x in xrange(40))
            self.header["report_id"] = date + nonce

        header_entry = self.header.copy()
        header_entry["record_type"] = "report_header"

        self.write_json_entry(header_entry, self.raw_fh)
        sanitised_header = self.sanitise_header(header_entry)
        self.write_json_entry(sanitised_header, self.sanitised_fh)

    def sanitise_entry(self, entry):
        # XXX we probably want to ignore these sorts of tests
        if not self.header.get('test_name'):
            self.failure("MISSING TEST_NAME", "sanitise_entry")
            return entry
        return sanitise.run(self.header['test_name'],
                            entry)

    def process_entry(self, entry):
        entry.update(self.header)
        entry["record_type"] = "measurement"

        self.write_json_entry(entry, self.raw_fh)
        sanitised_entry = self.sanitise_entry(entry)
        self.write_json_entry(sanitised_entry, self.sanitised_fh)

    def process(self):
        report = yaml.safe_load_all(self.in_fh)

        self.process_header(report)

        while True:
            try:
                entry = report.next()
                if not entry:
                    continue
                self.process_entry(entry)
                yield entry
            except StopIteration:
                self.done()
                break
            except Exception:
                self.failure(traceback.format_exc(), "process_entry")


class S3RawReportsImporter(luigi.Task):
    bucket = luigi.Parameter()
    filename = luigi.Parameter()
    tmp = luigi.Parameter()
    log_filename = luigi.Parameter()

    def get_uri(self):
        return "s3n://%s/%s" % (self.bucket, self.filename)

    def requires(self):
        return S3GzipTask(self.get_uri())

    @property
    def logfile(self):
        return os.path.join(self.tmp, 'streams.log')

    def complete(self):
        uri = self.input().path
        try:
            with open(self.log_filename) as f:
                for line in f:
                    if line.strip() == uri:
                        return True
        except:
            return False
        return False

    def output(self):
        filename = re.search('-(\d{4}-\d{2}-\d{2})T', self.filename).group(1)
        raw_dst = os.path.join(self.tmp, "streams",
                               "%s-raw.json" % filename)
        sanitised_dst = os.path.join(self.tmp, "streams",
                                     "%s-sanitised.json" % filename)
        return {
            "sanitised": luigi.LocalTarget(sanitised_dst),
            "raw": luigi.LocalTarget(raw_dst)
        }

    def run(self):
        o = self.output()
        i = self.input()
        with ReportProcessor(i, o['raw'], o['sanitised'], self.log_filename) as reports:
            for entry in reports.process():
                pass

class ReportStreams(luigi.Task):
    date = luigi.DateParameter()
    report_dir = luigi.Parameter()

    def output(self):
        filename = self.date.strftime('streams/%Y-%m-%d.json')
        return luigi.LocalTarget(os.path.join(self.report_dir, filename))


class StreamTMPToHDFS(luigi.Task):
    date = luigi.DateParameter()
    report_dir = luigi.Parameter()

    def requires(self):
        return ReportStreams(date=self.date,
                             report_dir=self.report_dir)

    def output(self):
        filename = self.date.strftime('streams/%Y-%m-%d.json')
        return luigi.hdfs.HdfsTarget(os.path.join('/reports', filename))

    def run(self):
        output = self.output()
        if output.exists():
            output.remove()

        with self.input().open('r') as in_file:
            with output.open('w') as out_file:
                shutil.copyfileobj(in_file, out_file)


class StreamsSanitiser(luigi.Task):
    date_interval = luigi.DateIntervalParameter()
    report_dir = luigi.Parameter()

    def requires(self):
        tasks = []
        for date in self.date_interval:
            tasks.append(ReportStreams(date=date,
                                       report_dir=self.report_dir))
        return tasks

    def run(self):
        pass

if __name__ == "__main__":
    luigi.interface.setup_interface_logging()
    sch = luigi.scheduler.CentralPlannerScheduler()
    tasks = []
    worker_processes = 16
    idx = 0
    w = luigi.worker.Worker(scheduler=sch,
                            worker_processes=worker_processes)

    log_filename = datetime.now().strftime("reports-%Y-%m-%dT%H%M%S.imported")
    for bucket, filename in list_raw_reports():
        print "Working on %s" % filename
        task = S3RawReportsImporter(bucket=bucket,
                                    filename=filename,
                                    tmp='/data1',
                                    log_filename=log_filename)
        w.add(task)
        idx += 1
    w.run()
    w.stop()
