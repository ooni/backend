from luigi.configuration import get_config
kafka_hosts = config.get('kafka', 'hosts')

"""
# This is using pykafka, but it's not on pypi...

from pykafka import KafkaClient
config = get_config()
client = KafkaClient()
raw_topic = client.topics['raw']
consumer = topic.get_simple_consumer(kafka_hosts)
for message in consumer:
    if message is not None:
        print message.offset, message.value

"""
from kafka import KafkaConsumer

# more advanced consumer -- multiple topics w/ auto commit offset
# management
consumer = KafkaConsumer('raw', 'sanitised',
                        bootstrap_servers=[kafka_hosts],
                        group_id='report_processor',
                        auto_commit_enable=True,
                        auto_commit_interval_ms=30 * 1000,
                        auto_offset_reset='smallest')

# Infinite iteration
for message in consumer:
    print("%s:%d:%d: key=%s value=%s" % (message.topic, message.partition,
                                         message.offset, message.key,
                                         message.value))

    # Mark this message as fully consumed
    # so it can be included in the next commit
    #
    # **messages that are not marked w/ task_done currently do not commit!
    kafka.task_done(message)
