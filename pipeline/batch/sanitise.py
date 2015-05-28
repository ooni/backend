import os
import json

import luigi
import luigi.worker
import luigi.hdfs
from luigi.task import ExternalTask
from luigi.configuration import get_config

from pipeline.helpers.report import Report
from pipeline.helpers.util import json_dumps, yaml_dump
from pipeline.helpers.util import list_report_files, get_luigi_target


class AggregateYAMLReports(ExternalTask):
    src = luigi.Parameter()
    dst_private = luigi.Parameter()
    dst_public = luigi.Parameter()
    bridge_db = luigi.Parameter()

    date = luigi.DateParameter()

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
        with target.open('r') as in_file:
            report = Report(in_file, self.bridge_db)
            print("Working it")
            for sanitised_entry, raw_entry in report.entries():
                s_data = json_dumps(sanitised_entry)
                sanitised_streams.write(s_data)
                sanitised_streams.write("\n")
                print("Writing")
                print(s_data)
                raw_streams.write(json_dumps(raw_entry))
                raw_streams.write("\n")
                yaml_dump(sanitised_entry, sanitised_yaml)
        sanitised_yaml.close()

    def run(self):
        config = get_config()
        output = self.output()
        raw_streams = output["raw_streams"].open('w')
        sanitised_streams = output["sanitised_streams"].open('w')

        reports_path = os.path.join(self.src,
                                    self.date.strftime("%Y-%m-%d"))
        print("Listing path %s" % reports_path)
        for filename in list_report_files(reports_path,
                                          config.get("s3", "aws_access_key_id"),
                                          config.get("s3", "aws_secret_access_key")):
            print("Got filename %s" % filename)
            self.process_report(filename, sanitised_streams, raw_streams)
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


def run(src, dst_private, dst_public, date_interval, bridge_db_path,
        worker_processes=16):

    with get_luigi_target(bridge_db_path).open('r') as f:
        bridge_db = json.load(f)

    luigi.interface.setup_interface_logging()
    sch = luigi.scheduler.CentralPlannerScheduler()
    w = luigi.worker.Worker(scheduler=sch,
                            worker_processes=worker_processes)

    from luigi import date_interval as d
    interval = None
    for c in [d.Year, d.Month, d.Week, d.Date, d.Custom]:
        interval = c.parse(date_interval)
        if interval:
            break
    if interval is None:
        raise ValueError("Invalid date interval")

    for date in interval:
        print("Working on %s" % date)
        task = AggregateYAMLReports(dst_private=dst_private,
                                    dst_public=dst_public, src=src, date=date,
                                    bridge_db=bridge_db)
        w.add(task)
    w.run()
    w.stop()
