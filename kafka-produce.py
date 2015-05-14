import os
import sys

from kafka import KafkaClient, SimpleProducer
from boto.s3.connection import S3Connection

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from helpers.settings import config

folder = 'reports'
access_key_id = config["aws"]["access-key-id"]
secret_access_key = config["aws"]["secret-access-key"]
bucket_name = config["aws"]["s3-bucket-name"]

kafka_client = KafkaClient(config['kafka']['hosts'])
simple_producer = SimpleProducer(kafka_client)
s3_connection = S3Connection(access_key_id, secret_access_key)
bucket = s3_connection.get_bucket(bucket_name)

for key in bucket.list(folder):
    report_uri = "s3://%s/%s" % (bucket_name, key.name)
    simple_producer.send_messages("report-uris", str(report_uri))
