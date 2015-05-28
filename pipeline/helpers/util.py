from __future__ import absolute_import, print_function, unicode_literals

# XXX add support for python 3
from urlparse import urlparse
import base64
import json
import os

import yaml


def encode_basestring_ascii(o):
    try:
        return encode_basestring_ascii_orig(o)
    except UnicodeDecodeError:
        return json.dumps({"base64": base64.b64encode(o)})
encode_basestring_ascii_orig = json.encoder.encode_basestring_ascii
json.encoder.encode_basestring_ascii = encode_basestring_ascii


def json_default(o):
    if isinstance(o, set):
        return list(o)
    return {"error": "could-not-serialize %s" % str(o)}


def json_dump(data, fh):
    encoder = json.JSONEncoder(ensure_ascii=True, default=json_default)
    for chunk in encoder.iterencode(data):
        fh.write(chunk)


def json_dumps(data):
    encoder = json.JSONEncoder(ensure_ascii=True, default=json_default)
    return encoder.encode(data)


def yaml_dump(data, fh):
    yaml.safe_dump(data, fh, explicit_start=True, explicit_end=True)


def _walk_local_directory(directory):
    for root, dirs, files in os.walk(directory):
        for filename in files:
            yield os.path.join(root, filename)


def _s3_walker(aws_access_key_id, aws_secret_access_key):
    from boto.s3.connection import S3Connection
    con = S3Connection(aws_access_key_id, aws_secret_access_key)

    def _walk_s3_directory(directory):
        p = urlparse(directory)
        bucket_name = p.netloc
        bucket = con.get_bucket(bucket_name)
        keys = bucket.list(p.path[1:])
        for key in keys:
            yield "s3n://" + os.path.join(bucket_name, key.name)
    return _walk_s3_directory


def list_report_files(directory, aws_access_key_id=None,
                      aws_secret_access_key=None):
    def is_report_file(filename):
        possible_extensions = (".yamloo", ".yamloo.gz", ".yaml", "yaml.gz")
        if any(filename.endswith(ext) for ext in possible_extensions):
            return True
        return False

    if directory.startswith("s3n://"):
        assert aws_access_key_id is not None
        assert aws_secret_access_key is not None
        walker = _s3_walker(aws_access_key_id, aws_secret_access_key)
    else:
        walker = _walk_local_directory
    for path in walker(directory):
        if is_report_file(path):
            yield path


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
