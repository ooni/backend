from luigi.configuration import get_config
from pykafka import KafkaClient
config = get_config()
client = KafkaClient(config.get('kafka', 'hosts'))
raw_topic = client.topics['raw']
consumer = topic.get_simple_consumer()
for message in consumer:
    if message is not None:
        print message.offset, message.value
