from __future__ import absolute_import, print_function, unicode_literals

from invoke.config import Config
from invoke import Collection, ctask as task
from pipeline.helpers.util import setup_pipeline_logging, Timer

config = Config(runtime_path="invoke.yaml")
logger = setup_pipeline_logging(config)


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
def generate_streams(ctx, src, date_interval, workers=16,
                     dst_private="s3n://ooni-private/",
                     dst_public="s3n://ooni-public/",
                     bridge_db_path="s3n://ooni-private/bridge_reachability/bridge_db.json"):
    timer = Timer()
    timer.start()
    from pipeline.batch import sanitise
    _create_luigi_cfg()
    sanitise.run(dst_private=dst_private, dst_public=dst_public, src=src,
                 date_interval=date_interval, bridge_db_path=bridge_db_path,
                 worker_processes=workers)
    logger.info("generate_streams runtime: %s" % timer.stop())


@task
def upload_reports(ctx, src, dst="s3n://ooni-private/reports-raw/yaml/",
                   workers=16, limit=None):
    timer = Timer()
    timer.start()
    if limit is not None:
        limit = int(limit)
    from pipeline.batch import upload_reports
    _create_luigi_cfg()
    upload_reports.run(src_directory=src, dst=dst, worker_processes=workers,
                       limit=limit)
    logger.info("upload_reports runtime: %s" % timer.stop())


@task
def list_reports(ctx):
    timer = Timer()
    timer.start()
    _create_luigi_cfg()
    from pipeline.helpers.util import list_report_files
    for f in list_report_files("s3n://ooni-private/reports-raw/yaml/2013-05-03",
                               config["aws"]["access_key_id"],
                               config["aws"]["secret_access_key"]):
        print(f)
    logger.info("list_reports runtime: %s" % timer.stop())

ns = Collection(upload_reports, generate_streams, list_reports)
