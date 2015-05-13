from __future__ import absolute_import, print_function, unicode_literals

from streamparse.bolt import Bolt

from kafka import KafkaClient, KeyedProducer, SimpleProducer
from helpers.settings import config
from helpers.util import json_dumps


class KafkaBolt(Bolt):

    def initialize(self, conf, ctx):
        self.kafka_client = KafkaClient(config['kafka']['hosts'])
        self.keyed_producer = KeyedProducer(self.kafka_client)
        self.simple_producer = SimpleProducer(self.kafka_client)

    def process(self, tup):
        report_id, record_type, report = tup.values
        json_data = json_dumps(report)
        report_id = str(report_id)
        topic = str("sanitised")
        if record_type == "entry":
            payload = str("e" + json_data)
        elif record_type == "header":
            payload = str("h" + json_data)
        elif record_type == "footer":
            payload = str("f" + json_data)
        self.keyed_producer.send(topic, report_id, payload)
        self.log('Processing: %s' % report_id)
