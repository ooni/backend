import os
import json
import logging
import traceback

import luigi
import luigi.worker
import luigi.hdfs
from luigi.task import ExternalTask

from invoke.config import Config

from pipeline.helpers.report import Report
from pipeline.helpers.util import json_dumps, yaml_dump, get_date_interval
from pipeline.helpers.util import list_report_files, get_luigi_target

config = Config(runtime_path="invoke.yaml")
logger = logging.getLogger('ooni-pipeline')


class AggregateYAMLReports(ExternalTask):
    src = luigi.Parameter()
    dst_private = luigi.Parameter()
    dst_public = luigi.Parameter()

    date = luigi.DateParameter()
    bridge_db = {}

    def output(self):
        sanitised_streams = get_luigi_target(os.path.join(
            self.dst_public,
            "reports-sanitised",
            "streams",
            self.date.strftime("%Y-%m-%d.json")
        ))
        raw_streams = get_luigi_target(os.path.join(
            self.dst_private,
            "reports-raw",
            "streams",
            self.date.strftime("%Y-%m-%d.json")
        ))
        return {
            "raw_streams": raw_streams,
            "sanitised_streams": sanitised_streams
        }

    def process_report(self, filename, sanitised_streams, raw_streams):
        target = get_luigi_target(filename)
        sanitised_yaml_filename = os.path.basename(filename)
        if not sanitised_yaml_filename.endswith(".gz"):
            sanitised_yaml_filename = sanitised_yaml_filename + ".gz"
        sanitised_yaml = get_luigi_target(os.path.join(
            self.dst_public,
            "reports-sanitised",
            "yaml",
            self.date.strftime("%Y-%m-%d"),
            sanitised_yaml_filename
        )).open('w')
        logger.info("Sanitising %s" % filename)
        with target.open('r') as in_file:
            report = Report(in_file, self.bridge_db, target.path)
            for sanitised_entry, raw_entry in report.entries():
                try:
                    logger.debug("writing sanitised entry to stream")
                    sanitised_streams.write(json_dumps(sanitised_entry))
                    sanitised_streams.write("\n")
                    logger.debug("writing raw entry to stream")
                    raw_streams.write(json_dumps(raw_entry))
                    raw_streams.write("\n")
                    logger.debug("writing sanitised yaml file")
                    yaml_dump(sanitised_entry, sanitised_yaml)
                except Exception:
                    logger.error("error in dumping %s" % filename)
                    logger.error(traceback.format_exc())
        sanitised_yaml.close()

    def run(self):
        with get_luigi_target(config.ooni.bridge_db_path).open('r') as f:
            self.bridge_db = json.load(f)

        output = self.output()
        raw_streams = output["raw_streams"].open('w')
        sanitised_streams = output["sanitised_streams"].open('w')

        reports_path = os.path.join(self.src,
                                    self.date.strftime("%Y-%m-%d"))
        logger.debug("listing path %s" % reports_path)
        for filename in list_report_files(reports_path,
                                          config.aws.access_key_id,
                                          config.aws.secret_access_key):
            logger.debug("got filename %s" % filename)
            try:
                self.process_report(filename, sanitised_streams, raw_streams)
            except Exception:
                logger.error("error in processing %s" % filename)
                logger.error(traceback.format_exc())
        raw_streams.close()
        sanitised_streams.close()


class RawReportsSanitiser(luigi.Task):
    src = luigi.Parameter()
    dst_private = luigi.Parameter()
    dst_public = luigi.Parameter()

    date_interval = luigi.DateIntervalParameter()

    def requires(self):
        return [
            AggregateYAMLReports(dst_private=self.dst_private,
                                 dst_public=self.dst_public, src=self.src,
                                 date=date)
            for date in self.date_interval
        ]


def run(src, dst_private, dst_public, date_interval, worker_processes=16):

    sch = luigi.scheduler.CentralPlannerScheduler()
    w = luigi.worker.Worker(scheduler=sch,
                            worker_processes=worker_processes)

    interval = get_date_interval(date_interval)
    for date in interval:
        logger.debug("working on %s" % date)
        task = AggregateYAMLReports(dst_private=dst_private,
                                    dst_public=dst_public, src=src, date=date)
        w.add(task)
    w.run()
    w.stop()
