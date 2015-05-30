from __future__ import absolute_import, print_function, unicode_literals

import os

from invoke.config import Config
from invoke import Collection, ctask as task
from pipeline.helpers.util import setup_pipeline_logging, Timer

config = Config(runtime_path="invoke.yaml")
logger = setup_pipeline_logging(config)


def _create_cfg_files():
    with open("client.cfg", "w") as fw:
        fw.write("""[core]
hdfs-tmp-dir: {tmp_dir}
local-tmp-dir: {tmp_dir}
[aws]
access-key-id: {aws_access_key_id}
secret-access-key: {aws_secret_access_key}
[s3]
aws_access_key_id: {aws_access_key_id}
aws_secret_access_key: {aws_secret_access_key}
[kafka]
hosts: {kafka_hosts}
[postgres]
local-tmp-dir: {tmp_dir}
""".format(tmp_dir=config.core.tmp_dir,
           aws_access_key_id=config.aws.access_key_id,
           aws_secret_access_key=config.aws.secret_access_key,
           kafka_hosts=config.kafka.hosts))
    with open("logging.cfg", "w") as fw:
        fw.write("""[loggers]
keys=root,ooni-pipeline,luigi-interface

[handlers]
keys=stream_handler,file_handler

[formatters]
keys=formatter

[logger_root]
level={loglevel}
handlers=

[logger_luigi-interface]
level=WARNING
handlers=stream_handler,file_handler
qualname=luigi-interface

[logger_ooni-pipeline]
level={loglevel}
handlers=stream_handler,file_handler
qualname=ooni-pipeline

[handler_stream_handler]
class=StreamHandler
level={loglevel}
formatter=formatter
args=(sys.stdout,)

[handler_file_handler]
class=FileHandler
level={loglevel}
formatter=formatter
args=('{logfile}',)

[formatter_formatter]
""".format(loglevel=config.logging.level, logfile=config.logging.filename))
        fw.write("format=%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        fw.write("\n")

_create_cfg_files()


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
    logger.info("generating streams from {src} for"
                " date {date_interval}".format(
                    src=src,
                    date_interval=date_interval
                ))

    logger.info("writing to public directory {dst_public} and "
                " private directory {dst_private}".format(
                    dst_public=dst_public, dst_private=dst_private
                ))

    from pipeline.batch import sanitise
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
    upload_reports.run(src_directory=src, dst=dst, worker_processes=workers,
                       limit=limit)
    logger.info("upload_reports runtime: %s" % timer.stop())


@task
def list_reports(ctx):
    timer = Timer()
    timer.start()
    from pipeline.helpers.util import list_report_files
    for f in list_report_files("s3n://ooni-private/reports-raw/yaml/2013-05-03",
                               config["aws"]["access_key_id"],
                               config["aws"]["secret_access_key"]):
        print(f)
    logger.info("list_reports runtime: %s" % timer.stop())


@task
def clean_streams(ctx, dst_private="s3n://ooni-private/",
                  dst_public="s3n://ooni-public/"):
    from pipeline.helpers.util import get_luigi_target
    paths_to_delete = (
        os.path.join(dst_private, "reports-raw", "streams"),
        os.path.join(dst_public, "reports-sanitised", "yaml"),
        os.path.join(dst_public, "reports-sanitised", "streams")
    )
    for path in paths_to_delete:
        target = get_luigi_target(path)
        logger.info("deleting %s" % path)
        target.remove()

@task
def add_headers_to_db(ctx, date_interval, workers=16,
                      src="s3n://ooni-private/reports-raw/yaml/",
                      dst_private="s3n://ooni-private/",
                      dst_public="s3n://ooni-public/",
                      bridge_db_path="s3n://ooni-private/bridge_reachability/bridge_db.json"):
    timer = Timer()
    timer.start()
    from pipeline.batch import add_headers_to_db
    add_headers_to_db.run(src=src, date_interval=date_interval,
                          worker_processes=workers, dst_private=dst_private,
                          dst_public=dst_public, bridge_db_path=bridge_db_path)
    logger.info("add_headers_to_db runtime: %s" % timer.stop())

@task
def start_computer(ctx, private_key):
    os.environ["ANSIBLE_HOST_KEY_CHECKING"] = "false"
    os.environ["AWS_ACCESS_KEY_ID"] = config.aws.access_key_id
    os.environ["AWS_SECRET_ACCESS_KEY"] = config.aws.secret_access_key
    ctx.run("ansible-playbook --private-key %s -i inventory playbook.yaml" % private_key, pty=True)

ns = Collection(upload_reports, generate_streams, list_reports, clean_streams, add_headers_to_db, start_computer)
