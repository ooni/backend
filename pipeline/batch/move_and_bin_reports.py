from __future__ import absolute_import, print_function, unicode_literals

import os
import shutil
import logging

from dateutil.parser import parse as date_parse
import datetime

import luigi
import luigi.worker
import luigi.hdfs
from luigi.task import ExternalTask
from luigi.format import GzipFormat
from luigi.s3 import S3Target
from luigi.file import LocalTarget

from invoke.config import Config

from pipeline.helpers.util import list_report_files

config = Config(runtime_path="invoke.yaml")
logger = logging.getLogger('ooni-pipeline')


class ReportSource(ExternalTask):
    src = luigi.Parameter()

    def output(self):
        file_format = None
        if self.src.endswith(".gz"):
            file_format = GzipFormat()
        if self.src.startswith("s3n://"):
            return S3Target(self.src, format=file_format)
        return LocalTarget(self.src, format=file_format)


class MoveAndBinReport(luigi.Task):
    src = luigi.Parameter()
    dst = luigi.Parameter()

    def requires(self):
        return ReportSource(self.src)

    def output(self):
        try:
            parts = os.path.basename(self.src).split("-")
            ext = parts[-1]
            # XXX this parsing stuff is insane...
            if ext.startswith("probe") or \
                    ext.startswith("backend"):
                date = date_parse('-'.join(parts[-5:-2]))
                asn = parts[-2]
                test_name = '-'.join(parts[:-5])
            elif parts[0].startswith("report"):
                date = date_parse('-'.join(parts[-3:-1]+parts[-1].split(".")[:1]))
                asn = "ASX"
                test_name = '-'.join(parts[1:-3])
                ext = "probe."+'.'.join(parts[-1].split(".")[1:])
            else:
                date = date_parse('-'.join(parts[-4:-1]))
                asn = parts[-1].split(".")[0]
                ext = "probe."+'.'.join(parts[-1].split(".")[1:])
                test_name = '-'.join(parts[:-4])
            # To facilitate sorting and splitting around "-" we convert the
            # date to be something like: 20150101T000015Z
            timestamp = date.strftime("%Y%m%dT%H%M%SZ")
            filename = "{date}-{asn}-{test_name}-{df_version}-{ext}".format(
                date=timestamp,
                asn=asn,
                test_name=test_name,
                df_version="v1",
                ext=ext.replace(".gz", "").replace(".yamloo", ".yaml")
            )
            uri = os.path.join(self.dst, datetime.date.today().isoformat(), filename)
        except Exception:
            uri = os.path.join(self.dst, "failed", os.path.basename(self.src))
        finally:
            if uri.startswith("s3n://"):
                return S3Target(uri)
            else:
                return LocalTarget(uri)

    def run(self):
        input = self.input()
        output = self.output()
        with output.open('w') as out_file:
            with input.open('r') as in_file:
                shutil.copyfileobj(in_file, out_file)
        input.remove()


def run(src_directory, dst):
    sch = luigi.scheduler.CentralPlannerScheduler()
    w = luigi.worker.Worker(scheduler=sch)

    for filename in list_report_files(
            src_directory, aws_access_key_id=config.aws.access_key_id,
            aws_secret_access_key=config.aws.secret_access_key):
        logging.info("moving %s to %s" % (filename, dst))
        task = MoveAndBinReport(src=filename, dst=dst)
        w.add(task, multiprocess=True)
    w.run()
