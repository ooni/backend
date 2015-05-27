import os
import time
import random
import string
# import StringIO
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
from util import json_dump, json_dumps

from kafka import KafkaClient, KeyedProducer, SimpleProducer


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


class S3GzipTask(ExternalTask):
    path = luigi.Parameter()

    def output(self):
        return S3Target(self.path, format=GzipFormat())


class ReportProcessor(object):
    _end_time = None
    _start_time = None

    def __init__(self, in_file, log_filename=None):
        self.in_file = in_file
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
        self._start_time = time.time()
        self.in_fh = self.in_file.open("r")

        self._report = yaml.safe_load_all(self.in_fh)
        self.process_header(self._report)

    def done(self):
        with open(self.log_filename, 'a') as fh:
            fh.write(self.in_file.path + "\n")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, value, traceback):
        if exc_type:
            self.failure(traceback, "exit")
        self.in_fh.close()

    def write_json_entry(self, entry, fh):
        json_dump(entry, fh)
        fh.write("\n")

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

        date = datetime.fromtimestamp(self._raw_header["start_time"])
        date = date.strftime("%Y-%m-%d")
        if not self._raw_header.get("report_id"):
            nonce = ''.join(random.choice(string.ascii_lowercase)
                            for x in xrange(40))
            self._raw_header["report_id"] = date + nonce

        header_entry = self._raw_header.copy()
        header_entry["record_type"] = "header"

        self._sanitised_header = self.sanitise_header(header_entry)

    def sanitise_entry(self, entry):
        # XXX we probably want to ignore these sorts of tests
        if not self._sanitised_header.get('test_name'):
            self.failure("MISSING TEST_NAME", "sanitise_entry")
            return entry
        return sanitise.run(self._raw_header['test_name'], entry)

    def process_entry(self, entry):
        entry["record_type"] = "measurement"

        raw_entry = entry.copy()
        sanitised_entry = entry.copy()

        raw_entry.update(self._raw_header)
        sanitised_entry.update(self._sanitised_header)
        sanitised_entry = self.sanitise_entry(sanitised_entry)
        return sanitised_entry, raw_entry

    @property
    def footer(self):
        raw = self._raw_header.copy()
        sanitised = self._sanitised_header.copy()
        if not self._end_time:
            self._end_time = time.time()

        extra_keys = {
            "record_type": "footer",
            'stage_1_process_time': self._start_time - self._end_time
        }

        raw.update(extra_keys)
        sanitised.update(extra_keys)

        return {
            "raw": raw,
            "sanitised": sanitised
        }

    def process(self):
        while True:
            try:
                entry = self._report.next()
                if not entry:
                    continue
                yield self.process_entry(entry)
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

    kafka_client = None

    def get_uri(self):
        return "s3n://%s/%s" % (self.bucket, self.filename)

    def requires(self):
        return S3GzipTask(self.get_uri())

    @property
    def logfile(self):
        return os.path.join(self.tmp, 'streams.log')

    def publish(self, data, topic, data_type):
        message = json_dumps(data)

        producer = KeyedProducer(self.kafka_client)
        producer.send(topic, data['report_id'], data_type + message)

    def finished(self, topic):
        producer = SimpleProducer(self.kafka_client)
        producer.send_messages(topic, 'd')

    def run(self):
        config = get_config()

        self.kafka_client = KafkaClient(config.get('kafka', 'hosts'))

        i = self.input()
        with ReportProcessor(i, self.log_filename) as reports:
            self.publish(reports.header['raw'], 'raw', 'h')
            self.publish(reports.header['sanitised'], 'sanitised', 'h')
            for sanitised_entry, raw_entry in reports.process():
                self.publish(raw_entry, 'raw', 'e')
                self.publish(sanitised_entry, 'sanitised', 'e')
            footer = reports.footer
            self.publish(footer['raw'], 'raw', 'f')
            self.publish(footer['sanitised'], 'sanitised', 'f')
        self.finished('raw')
        self.finished('sanitised')

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
