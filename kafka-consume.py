import os
import time
import json
import shutil
from datetime import datetime
from StringIO import StringIO

from kafka import KafkaConsumer
from kafka.common import ConsumerTimeout


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

    def __init__(self, consumer, suffix, timeout=30):
        self.consumer = consumer
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
            print "Got a footer"
            report = json.loads(data[1:])
            self.add_to_date_bucket(report)
        elif data[0] == 'd':
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
            print("Flushing date bucket %s" % report_date)
            self.flush_date_bucket(report_date)
        else:
            print("Date bucket is not yet full current size: %s" %
                  self.date_buckets[report_date].len)


def consume_messages(raw_bucket_manager, sanitised_bucket_manager):
    for message in consumer:
        if message.topic == 'raw':
            raw_bucket_manager.add_message(message)
        elif message.topic == 'sanitised':
            sanitised_bucket_manager.add_message(message)

bucket_timeout = 30
kafka_hosts = "manager.infra.ooni.nu:6667"
consumer = KafkaConsumer('raw', 'sanitised',
                         metadata_broker_list=[kafka_hosts],
                         group_id='report_processor',
                         auto_commit_enable=True,
                         consumer_timeout_ms=bucket_timeout * 1000,
                         auto_commit_interval_ms=30 * 1000,
                         auto_offset_reset='smallest')

raw_bucket_manager = BucketManager(consumer, '.raw', bucket_timeout)
sanitised_bucket_manager = BucketManager(consumer, '.sanitised',
                                         bucket_timeout)

while True:
    try:
        consume_messages(raw_bucket_manager, sanitised_bucket_manager)
    except ConsumerTimeout:
        raw_bucket_manager.check_timeouts()
        sanitised_bucket_manager.check_timeouts()
