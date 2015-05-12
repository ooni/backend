from __future__ import absolute_import, print_function, unicode_literals

from streamparse.bolt import Bolt

from kafka import KafkaClient, KeyedProducer, SimpleProducer


class KafkaBolt(Bolt):

    def initialize(self, conf, ctx):
        self.kafka_client = KafkaClient(conf['kafka']['hosts'])
        self.keyed_producer = KeyedProducer(self.kafka_client)
        self.simple_producer = SimpleProducer(self.kafka_client)

    def process(self, tup):
        report_id, record_type, json_data = tup.values
        if record_type == "entry":
            self.keyed_producer.send('sanitised', report_id, 'e' + json_data)
        elif record_type == "header":
            self.keyed_producer.send('sanitised', report_id, 'h' + json_data)
        elif record_type == "footer":
            self.keyed_producer.send('sanitised', report_id, 'f' + json_data)
        self.log('%s: %s' % (report_id, json_data))
