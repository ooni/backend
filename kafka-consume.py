import os
import json
import shutil
from datetime import datetime
from StringIO import StringIO
from luigi.configuration import get_config
from kafka import KafkaConsumer


class BucketManager(object):
    max_bucket_size = 1024 * 1024 * 64
    output_dir = '/data1/reports/'

    def __init__(self):
        self.date_buckets = {}
        self.report_buckets = {}

    def flush_date_bucket(self, date):
        self.date_buckets[date].seek(0)
        with open(os.path.join(self.output_dir, date), 'a+') as f:
            shutil.copyfileobj(self.date_buckets[date], f)
        del self.date_buckets[date]

    def add_to_report_bucket(self, report_id, data):
        if not self.report_buckets.get(report_id):
            self.report_buckets[report_id] = StringIO()
        self.report_buckets[report_id].write(data[1:])
        self.report_buckets[report_id].write("\n")

        if data[0] == 'f':
            report = json.loads(data[1:])
            self.add_to_date_bucket(report)

    def add_to_date_bucket(self, report):
        report_date = datetime.fromtimestamp(
            report['start_time']).strftime('%Y-%m-%d')
        report_id = report['report_id']
        if not self.date_buckets.get(report_date):
            self.date_buckets[report_date] = StringIO()

        self.report_buckets[report_id].seek(0)
        self.date_buckets[report_date].write(
            self.report_buckets[report_id].read()
        )
        del self.report_buckets[report_id]
        if self.date_buckets[report_date].len > self.max_bucket_size:
            self.flush_date_bucket(report_date)

config = get_config()
kafka_hosts = config.get('kafka', 'hosts')

bucket_manager = BucketManager()
consumer = KafkaConsumer('raw', 'sanitised',
                         metadata_broker_list=[kafka_hosts],
                         group_id='report_processor',
                         auto_commit_enable=True,
                         auto_commit_interval_ms=30 * 1000,
                         auto_offset_reset='smallest')

# Infinite iteration
for message in consumer:
    print("%s:%d:%d: key=%s value=%s" % (message.topic, message.partition,
                                         message.offset, message.key,
                                         message.value))

    bucket_manager.add_to_report_bucket(message.key, message.value)
    consumer.task_done(message)
