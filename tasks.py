from __future__ import absolute_import, print_function, unicode_literals

from invoke.config import Config
from invoke import Collection, ctask as task

config = Config(runtime_path="invoke.yaml")


def _create_luigi_cfg():
    with open("client.cfg", "w") as fw:
        fw.write("[aws]\n")
        fw.write("access-key-id: %s\n" % config.aws.access_key_id)
        fw.write("secret-access-key: %s\n" % config.aws.secret_access_key)
        fw.write("[s3]\n")
        fw.write("aws_access_key_id: %s\n" % config.aws.access_key_id)
        fw.write("aws_secret_access_key: %s\n" % config.aws.secret_access_key)
        fw.write("[kafka]\n")
        fw.write("hosts: %s\n" % config.kafka.hosts)


@task
def realtime(ctx):
    print("Starting realtime stream processing")


@task
def generate_streams(ctx, src, date_interval,
                     dst_private="s3n://ooni-private/",
                     dst_public="s3n://ooni-public/"):
    from pipeline.batch import sanitise
    _create_luigi_cfg()
    sanitise.run(dst_private=dst_private, dst_public=dst_public, src=src,
                 date_interval=date_interval)


@task
def upload_reports(ctx, src, dst="s3n://ooni-private/reports-raw/yaml/",
                   workers=16, limit=None):
    if limit is not None:
        limit = int(limit)
    from pipeline.batch import upload_reports
    _create_luigi_cfg()
    upload_reports.run(src_directory=src, dst=dst, worker_processes=workers,
                       limit=limit)

ns = Collection(upload_reports)
