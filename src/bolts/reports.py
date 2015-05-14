from __future__ import absolute_import, print_function, unicode_literals
import os
import traceback

from streamparse.bolt import Bolt

from kafka import KafkaClient, KeyedProducer, SimpleProducer
from helpers.settings import config
from helpers.util import json_dumps

from helpers.s3 import S3Downloader
from helpers.report import Report


class ReportParseBolt(Bolt):
    def initialize(self, stormconf, ctx):
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
            self.emit([report_id, record_type, s_report_data])
        in_file.close()
        os.remove(in_file.name)

    def process(self, tup):
        report_uri = tup.values[0]
        if report_uri.startswith('s3'):
            in_file = self.s3_downloader.download(report_uri)
        else:
            self.fail(tup)
            raise Exception("Unsupported URI")

        try:
            self.process_report(in_file)
        except Exception as exc:
            self.fail(tup)
            print(traceback.format_exc())
            raise exc

class KafkaBolt(Bolt):

    def initialize(self, stormconf, ctx):
        self.kafka_client = KafkaClient(config['kafka']['hosts'])
        self.keyed_producer = KeyedProducer(self.kafka_client)
        self.simple_producer = SimpleProducer(self.kafka_client)

    def process(self, tup):
        report_id, record_type, report_data = tup.values
        self.log('Processing: %s' % report_id)
        json_data = str(report_data)
        report_id = str(report_id)
        topic = str("sanitised")
        if record_type == "entry":
            payload = str("e" + json_data)
        elif record_type == "header":
            payload = str("h" + json_data)
        elif record_type == "footer":
            payload = str("f" + json_data)
        self.keyed_producer.send(topic, report_id, payload)
