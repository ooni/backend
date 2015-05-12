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

    def __init__(self, consumer, suffix):
        self.consumer = consumer
        self.suffix = suffix
        self.date_buckets = {}
        self.report_buckets = {}
        self.message_queue_bucket = {
            'reports': {},
            'dates': {}
        }

    def flush_date_bucket(self, date):
        self.date_buckets[date].seek(0)
        with open(os.path.join(self.output_dir,
                               date + self.suffix), 'a+') as f:
            shutil.copyfileobj(self.date_buckets[date], f)
        while True:
            try:
                message = self.message_queue_bucket['dates'][date].pop()
                self.consumer.task_done(message)
            except IndexError:
                break
        del self.date_buckets[date]
        # Let's also flush the consumer commit log
        self.consumer.commit()

    def flush_all(self):
        for date, _ in self.date_buckets.items():
            self.flush_date_bucket(date)

    def add_message(self, message):
        data = message.value
        report_id = message.key
        if not self.message_queue_bucket['reports'].get(report_id):
            self.message_queue_bucket['reports'][report_id] = []
        self.message_queue_bucket['reports'][report_id].append(message)

        if data[0] in ('e', 'h'):
            self.add_to_report_bucket(report_id, data[1:])
        elif data[0] == 'f':
            report = json.loads(data[1:])
            self.add_to_date_bucket(report)
        elif data[0] == 'd':
            self.flush_all()

    def add_to_report_bucket(self, report_id, report_data):
        if not self.report_buckets.get(report_id):
            self.report_buckets[report_id] = StringIO()
        self.report_buckets[report_id].write(report_data)
        self.report_buckets[report_id].write("\n")

    def add_to_date_bucket(self, report):
        report_date = datetime.fromtimestamp(
            report['start_time']).strftime('%Y-%m-%d')
        report_id = report['report_id']
        if not self.date_buckets.get(report_date):
            self.date_buckets[report_date] = StringIO()

        # Move the messages from the report bucket into the date bucket
        if not self.message_queue_bucket['dates'].get(report_date):
            self.message_queue_bucket['dates'][report_date] = []
        self.message_queue_bucket['dates'][report_date] += \
            self.message_queue_bucket['reports'].pop(report_id)

        # Move the reports from the report bucket into the date bucket
        self.report_buckets[report_id].seek(0)
        self.date_buckets[report_date].write(
            self.report_buckets[report_id].read()
        )
        del self.report_buckets[report_id]

        # If we have reached the acceptable block size we can flush to disk
        if self.date_buckets[report_date].len > self.max_bucket_size:
            self.flush_date_bucket(report_date)

config = get_config()
kafka_hosts = config.get('kafka', 'hosts')

consumer = KafkaConsumer('raw', 'sanitised',
                         bootstrap_servers=[kafka_hosts],
                         group_id='report_processor',
                         auto_commit_enable=True,
                         auto_commit_interval_ms=30 * 1000,
                         auto_offset_reset='smallest')

raw_bucket_manager = BucketManager(consumer, '.raw')
sanitised_bucket_manager = BucketManager(consumer, '.sanitised')

# Infinite iteration
for message in consumer:
    print("%s:%d:%d: key=%s value=%s" % (message.topic, message.partition,
                                         message.offset, message.key,
                                         message.value))

    if message.topic == 'raw':
        raw_bucket_manager.add_message(message)
    elif message.topic == 'sanitised':
        sanitised_bucket_manager.add_message(message)
