from luigi.configuration import get_config

config = get_config()
kafka_hosts = config.get('kafka', 'hosts')

from kafka import KafkaConsumer

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
    consumer.task_done(message)
