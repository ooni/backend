from __future__ import absolute_import, print_function, unicode_literals

from datetime import datetime
import json
import traceback
import sys
import os
#from functools import wraps

from invoke.config import Config
from invoke import Collection, ctask as task
from pipeline.helpers.util import setup_pipeline_logging, Timer

config = Config(runtime_path="invoke.yaml")
assert config._runtime_found, "you probably need to 'cp invoke.yaml.example invoke.yaml'"
logger = setup_pipeline_logging(config)

os.environ["PYTHONPATH"] = os.environ.get("PYTHONPATH") if os.environ.get("PYTHONPATH") else ""
os.environ["PYTHONPATH"] = ":".join(os.environ["PYTHONPATH"].split(":") + [config.core.ooni_pipeline_path])

#def with_timer(func_to_wrap):
#    @wraps(func_to_wrap)
#    def func_wrapper(*args, **kwargs):
#        logger.info("Starting task %s" % self.__name__)
#        timer = Timer()
#        timer.start()
#        func_to_wrap(*args, **kwargs)
#        logger.info("Finished task at %s" % timer.stop())
#    return func_wrapper

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
[spark]
spark-submit: {spark_submit}
master: {spark_master}
""".format(tmp_dir=config.core.tmp_dir,
           aws_access_key_id=config.aws.access_key_id,
           aws_secret_access_key=config.aws.secret_access_key,
           kafka_hosts=config.kafka.hosts,
           spark_master=config.spark.master,
           spark_submit=config.spark.spark_submit))

_create_cfg_files()

@task
def generate_streams(ctx, date_interval,
                     src="s3n://ooni-private/reports-raw/yaml/",
                     workers=16,
                     dst_private="s3n://ooni-private/",
                     dst_public="s3n://ooni-public/", halt=False):
    try:
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
                    date_interval=date_interval, worker_processes=workers)
        logger.info("generate_streams runtime: %s" % timer.stop())
    finally:
        if halt:
            ctx.run("sudo halt")


@task
def move_and_bin_reports(ctx, src, dst="s3n://ooni-private/reports-raw/yaml/"):
    timer = Timer()
    timer.start()
    from pipeline.batch import move_and_bin_reports
    move_and_bin_reports.run(src_directory=src, dst=dst)
    logger.info("move_and_bin_reports runtime: %s" % timer.stop())


@task
def list_reports(ctx, path="s3n://ooni-private/reports-raw/yaml/"):
    timer = Timer()
    timer.start()
    from pipeline.helpers.util import list_report_files
    for f in list_report_files(path,
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
        os.path.join(dst_public, "reports-sanitised", "streams"),
        os.path.join(dst_public, "json")
    )
    for path in paths_to_delete:
        target = get_luigi_target(path)
        logger.info("deleting %s" % path)
        target.remove()

@task
def add_headers_to_db(ctx, date_interval, workers=16,
                      src="s3n://ooni-private/reports-raw/yaml/",
                      dst_private="s3n://ooni-private/",
                      dst_public="s3n://ooni-public/"):
    timer = Timer()
    timer.start()
    from pipeline.batch import add_headers_to_db
    logger.info("Running add_headers_to_db for date %s" % date_interval)
    add_headers_to_db.run(src=src, date_interval=date_interval,
                        worker_processes=workers, dst_private=dst_private,
                        dst_public=dst_public)
    logger.info("add_headers_to_db runtime: %s" % timer.stop())

@task
def streams_to_db(ctx, streams_dir, date_interval):
    timer = Timer()
    timer.start()
    from pipeline.batch import streams_to_db
    streams_to_db.run(streams_dir=streams_dir, date_interval=date_interval)
    print("streams_to_db runtime: %s" % timer.stop())

@task
def bins_to_sanitised_streams(ctx, date_interval,
                              unsanitised_dir="s3n://ooni-private/reports-raw/",
                              sanitised_dir="s3n://ooni-public/",
                              workers=36):
    from pipeline.batch import bins_to_sanitised_streams
    bins_to_sanitised_streams.run(unsanitised_dir=unsanitised_dir,
                                  sanitised_dir=sanitised_dir,
                                  date_interval=date_interval,
                                  workers=workers)

@task
def spark_submit(ctx, script,
                 spark_submit="/home/hadoop/spark/bin/spark-submit"):
    timer = Timer()
    timer.start()
    ctx.run("{spark_submit} {script}".format(
        spark_submit=spark_submit,
        script=script
    ))
    logger.info("spark_submit runtime: %s" % timer.stop())


@task
def spark_apps(ctx, date_interval, src="s3n://ooni-public/reports-sanitised/streams/",
               dst="s3n://ooni-public/processed/", workers=3):
    timer = Timer()
    timer.start()
    from pipeline.batch import spark_apps
    logger.info("Running spark apps")
    spark_apps.run(date_interval=date_interval, src=src, dst=dst, worker_processes=workers)
    logger.info("spark_submit runtime: %s" % timer.stop())


ns = Collection(move_and_bin_reports, generate_streams, list_reports, clean_streams,
                spark_apps, spark_submit, bins_to_sanitised_streams, streams_to_db)
