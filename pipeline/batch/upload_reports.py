from __future__ import absolute_import, print_function, unicode_literals

import os
import shutil

from dateutil.parser import parse as date_parse

import luigi
import luigi.worker
import luigi.hdfs
from luigi.task import ExternalTask
from luigi.format import GzipFormat
from luigi.s3 import S3Target
from luigi.file import LocalTarget

from pipeline.helpers.util import list_report_files


class ReportSource(ExternalTask):
    src = luigi.Parameter()

    def output(self):
        file_format = None
        if self.src.endswith(".gz"):
            file_format = GzipFormat()
        if self.src.startswith("s3n://"):
            return S3Target(self.src, format=file_format)
        return LocalTarget(self.src, format=file_format)


class S3CopyRawReport(luigi.Task):
    src = luigi.Parameter()
    dst = luigi.Parameter()

    def requires(self):
        return ReportSource(self.src)

    def output(self):
        parts = os.path.basename(self.src).split("-")
        date = '-'.join(parts[-5:-2])
        # To facilitate sorting and splitting around "-" we convert the date to
        # be something like: 20150101T000015Z
        timestamp = date_parse(date).strftime("%Y%m%dT%H%M%SZ")
        filename = "{timestamp}-{asn}-{test_name}-{df_version}-{ext}".format(
            timestamp=timestamp,
            asn=parts[-2],
            test_name='-'.join(parts[:-5]),
            df_version="v1",
            ext=parts[-1].replace(".gz", "").replace(".yamloo", ".yaml")
        )
        uri = os.path.join(self.dst, filename)
        return S3Target(uri)

    def run(self):
        with self.input().open('r') as in_file:
            with self.output().open('w') as out_file:
                shutil.copyfileobj(in_file, out_file)


def run(src_directory, dst, worker_processes, limit=None):
    luigi.interface.setup_interface_logging()
    sch = luigi.scheduler.CentralPlannerScheduler()
    idx = 0
    w = luigi.worker.Worker(scheduler=sch,
                            worker_processes=worker_processes)

    for filename in list_report_files(src_directory):
        if limit is not None and idx >= limit:
            break
        idx += 1
        print("Working on %s" % filename)
        task = S3CopyRawReport(src=filename, dst=dst)
        w.add(task)
    w.run()
    w.stop()
