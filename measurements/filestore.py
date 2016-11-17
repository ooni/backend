import os
import errno

from six.moves.urllib.parse import urlparse, urljoin

import boto3
import botocore
from sqlalchemy import exists

from measurements.models import ReportFile

class S3NotConfigured(Exception):
    pass

class FileNotFound(Exception):
    pass

def init_s3(app):
    kwargs = dict(
        aws_access_key_id=app.config['S3_ACCESS_KEY_ID'],
        aws_secret_access_key=app.config['S3_SECRET_ACCESS_KEY'],
        aws_session_token=app.config['S3_SESSION_TOKEN'],
        endpoint_url=app.config['S3_ENDPOINT_URL']
    )
    app.s3_reports_bucket = None
    app.s3_reports_prefix = None
    app.s3_client = boto3.resource('s3', **kwargs)
    reports_url = urlparse(app.config['REPORTS_DIR'])
    if reports_url.scheme == 's3':
        app.s3_reports_bucket = app.s3_client.Bucket(reports_url.netloc)
        # We need to remove the leading "/"
        app.s3_reports_prefix  = reports_url.path[1:]

def init_filestore(app):
    app.s3_client = None
    if app.config['S3_ACCESS_KEY_ID']:
        init_s3(app)

def list_files_s3(app, target):
    assert target.startswith(app.config['REPORTS_DIR']), (
            "target must start with {}".format(app.config['REPORTS_DIR']))
    prefix = urlparse(target).path[1:]
    objects = app.s3_reports_bucket.objects.filter(
        Prefix=prefix
    )
    for obj_summary in objects:
        yield "s3://{}/{}".format(
            obj_summary.bucket_name, obj_summary.key
        )

def list_files_local(target):
    for dirname, _, filenames in os.walk(target):
        for filename in filenames:
            yield os.path.join(dirname, filename)

def list_files(app, target=None):
    if target is None:
        target = app.config['REPORTS_DIR']
    if app.s3_reports_bucket:
        return list_files_s3(app, target)
    return list_files_local(target)

def gen_file_chunks_fp(in_file):
    CHUNK_SIZE = 1024
    while True:
        data = in_file.read(CHUNK_SIZE)
        if not data:
            break
        yield data

def gen_file_chunks_local(filepath):
    try:
        content_length = os.path.getsize()
        with open(filepath) as in_file:
            return {
                'content': gen_file_chunks_fp(in_file),
                'content_length': content_length
            }
    except EnvironmentError as exc:
        # For python 2-3 compat
        if exc.errno == errno.EEXIST:
            raise FileNotFound
        else:
            raise exc

def gen_file_chunks_s3(app, filepath):
    if not app.s3_reports_bucket:
        raise S3NotConfigured

    # The s3 key must not have the leading /
    s3_key = urlparse(filepath).path[1:]
    try:
        resp = app.s3_reports_bucket.Object(s3_key).get()
    except botocore.exceptions.ClientError as exc:
        if exc.response['Error']['Code'] == "404":
            print(exc.reponse['Error'])
            raise FileNotFound
        else:
            raise exc
    return {
        'content': gen_file_chunks_fp(resp['Body']),
        'content_length': resp['ContentLength']
    }


def gen_file_chunks(app, filepath):
    if filepath.startswith("s3://"):
        # XXX this code path is actually never hit, because when using S3 we
        #  don't want to proxy requests, but we just wish to redirect users
        # to the s3 based endpoint and the download_url will always point to
        #  s3 directly.
        return gen_file_chunks_s3(app, filepath)
    return gen_file_chunks_local(filepath)

def get_download_url_s3(app, bucket_date, filename):
    url = app.config['REPORTS_DIR'].replace(
        "s3://",
        "https://s3.amazonaws.com/"
    )
    return os.path.join(url, bucket_date, filename)

def get_download_url(app, bucket_date, filename):
    if app.config['REPORTS_DIR'].startswith("s3://"):
        return get_download_url_s3(app, bucket_date, filename)
    return urljoin(
        app.config['BASE_URL'],
        '/files/download/{}'.format(filename)
    )

def add_to_db(app, filepath, index, no_check=False):
    if not filepath.endswith(".json"):
        return False
    report_file = ReportFile.from_filepath(filepath, index)

    if no_check is False:
        ret = app.db_session.query(
            exists().where(ReportFile.filename == report_file.filename)
        ).scalar()
        if ret is True:
            return False

    app.db_session.add(report_file)
    return True

def update_file_metadata(app, target_dir, no_check=False):
    most_recent_index = 0
    most_recent = app.db_session.query(ReportFile) \
        .order_by(ReportFile.idx.desc()) \
        .first()
    if most_recent is not None:
        most_recent_index = most_recent.idx

    idx = 0
    for filepath in list_files(app, target_dir):
        index = most_recent_index + idx
        if not add_to_db(app, filepath, index, no_check):
            continue
        idx += 1
        if idx % 100 == 0:
            app.db_session.commit()
    app.db_session.commit()
