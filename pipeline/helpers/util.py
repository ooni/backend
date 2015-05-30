from __future__ import absolute_import, print_function, unicode_literals

import zlib
import time
import logging
import logging.config
# XXX add support for python 3
from urlparse import urlparse
from base64 import b64encode
import os

import yaml
from pipeline.libs import simplejson

def json_default(o):
    if isinstance(o, set):
        return list(o)
    return {"error": "could-not-serialize %s" % str(o)}


def json_dumps(data):
    return simplejson.dumps(data, ensure_ascii=True, default=json_default)

def json_loads(data):
    return simplejson.loads(data)

def yaml_dump(data, fh):
    yaml.safe_dump(data, fh, explicit_start=True, explicit_end=True)


def _local_walker(recursive=True):
    def _walk_local_directory(directory):
        if recursive:
            for root, dirs, files in os.walk(directory):
                for filename in files:
                    yield os.path.join(root, filename)
        else:
            for path in os.listdir(directory):
                yield os.path.join(directory, filename)
    return _walk_local_directory


def _s3_walker(aws_access_key_id, aws_secret_access_key, recursive=True):
    from boto.s3.connection import S3Connection
    con = S3Connection(aws_access_key_id, aws_secret_access_key)

    def _walk_s3_directory(directory):
        p = urlparse(directory)
        bucket_name = p.netloc
        bucket = con.get_bucket(bucket_name)
        if recursive:
            keys = bucket.list(p.path[1:])
        else:
            keys = bucket.list(p.path[1:], "/")
        for key in keys:
            yield "s3n://" + os.path.join(bucket_name, key.name)
    return _walk_s3_directory


def list_report_files(directory, aws_access_key_id=None,
                      aws_secret_access_key=None, recursive=True):
    def is_report_file(filename):
        possible_extensions = (".yamloo", ".yamloo.gz", ".yaml", "yaml.gz")
        if any(filename.endswith(ext) for ext in possible_extensions):
            return True
        return False

    if directory.startswith("s3n://"):
        assert aws_access_key_id is not None
        assert aws_secret_access_key is not None
        walker = _s3_walker(aws_access_key_id=aws_access_key_id,
                            aws_secret_access_key=aws_secret_access_key,
                            recursive=recursive)
    else:
        walker = _walk_local_directory
    for path in walker(directory):
        if is_report_file(path):
            yield path

def get_imported_dates(directory,aws_access_key_id=None,
                       aws_secret_access_key=None):

    walker = _s3_walker(aws_access_key_id=aws_access_key_id,
                        aws_secret_access_key=aws_secret_access_key,
                        recursive=False)
    dates = []
    for date_directory in walker(directory):
        dates.append(date_directory.split("/")[-2])
    return dates

def get_luigi_target(path):
    from luigi.s3 import S3Target
    from luigi.file import LocalTarget
    from luigi.format import GzipFormat

    file_format = None
    if path.endswith(".gz"):
        file_format = GzipFormat()
    if path.startswith("s3n://"):
        return S3Target(path, format=file_format)
    return LocalTarget(path, format=file_format)

def setup_pipeline_logging(config, conf_file="logging.cfg"):
    if os.path.exists(conf_file):
        logging.config.fileConfig(conf_file, disable_existing_loggers=True)
    else:
        log_level = getattr(logging, config.logging.level)
        logger = logging.getLogger('ooni-pipeline')
        logger.setLevel(log_level)

        file_handler = logging.FileHandler(config.logging.filename)
        file_handler.setLevel(log_level)

        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
    return logging.getLogger('ooni-pipeline')

class Timer(object):
    def __init__(self):
        self.start_time = None
        self.end_time = None

    @property
    def runtime(self):
        if self.start_time is None:
            raise RuntimeError("Did not call start")
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    def start(self):
        self.start_time = time.time()

    def stop(self):
        self.end_time = time.time()
        return self.runtime


def get_date_interval(date_interval):
    from luigi import date_interval as d
    interval = None
    for c in [d.Year, d.Month, d.Week, d.Date, d.Custom]:
        interval = c.parse(date_interval)
        if interval:
            return interval
    raise ValueError("Invalid date interval")
