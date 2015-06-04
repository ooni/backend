# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals

import os
import logging

import luigi
import luigi.postgres
from luigi.task import ExternalTask
from luigi.contrib.spark import PySparkTask

from invoke.config import Config

from pipeline.helpers.util import json_loads, get_date_interval
from pipeline.helpers.util import get_luigi_target
from pipeline.helpers.util import get_imported_dates


config = Config(runtime_path="invoke.yaml")
logger = logging.getLogger('ooni-pipeline')


class FindInterestingReports(PySparkTask):
    driver_memory = '2g'
    executor_memory = '3g'
    py_packages = ["pipeline"]

    date = luigi.DateParameter()
    src = luigi.Parameter()
    dst = luigi.Parameter()

    test_name = "http_requests_test"
    software_name = "ooniprobe"

    def input(self):
        return get_luigi_target(os.path.join(self.src, "%s.json" % self.date))

    def output(self):
        output_path = os.path.join(self.dst,
                                   "{software_name}-{test_name}"
                                   "-interesting-{date}.json".format(
                                       date=self.date,
                                       test_name=self.test_name,
                                       software_name=self.software_name))
        return get_luigi_target(output_path)

    def main(self, sc, *args):
        from pyspark.sql import SQLContext
        sqlContext = SQLContext(sc)
        df = sqlContext.jsonFile(self.input().path)
        report_entries = df.filter("test_name = '{test_name}'"
                                   " AND record_type = 'entry'".format(
                                       test_name=self.test_name))
        interestings = self.find_interesting(report_entries)

        out_file = self.output().open('w')
        for interesting in interestings.toJSON().collect():
            out_file.write(interesting)
            out_file.write("\n")
        out_file.close()

    def find_interesting(self, report_entries):
        raise NotImplemented("You must implement a find_interesting method")


class HTTPRequestsInterestingFind(FindInterestingReports):
    test_name = "http_requests_test"

    def find_interesting(self, report_entries):
        return report_entries.filter("body_length_match = false"
                                     " OR headers_match = false")


class InterestingToDB(luigi.postgres.CopyToTable):
    src = luigi.Parameter()
    date = luigi.DateParameter()
    dst = luigi.Parameter()

    host = str(config.postgres.host)
    database = str(config.postgres.database)
    user = str(config.postgres.username)
    password = str(config.postgres.password)
    table = 'spark_results'

    columns = [
        ("report_id", "TEXT"),
        ("report_filename", "TEXT"),
        ("input", "TEXT"),
    ]

    finder = FindInterestingReports

    def requires(self):
        f = self.finder(src=self.src, date=self.date, dst=self.dst)
        logger.info("Running the finder %s" % f)
        return f

    def rows(self):
        with self.input().open('r') as in_file:
            for line in in_file:
                record = json_loads(line.decode('utf-8', 'ignore').strip('\n'))
                logger.info("Adding to DB %s" % (record["report_id"]))
                yield self.serialize(record)

    def serialize(self, record):
        return [record.report_id, record.report_filename, record.input]


class HTTPRequestsToDB(InterestingToDB):
    table = 'http_requests_interesting'

    columns = [
        ("report_id", "TEXT"),
        ("report_filename", "TEXT"),
        ("input", "TEXT")
    ]
    finder = HTTPRequestsInterestingFind

    def serialize(self, record):
        return [record["report_id"], record["report_filename"],
                record["input"]]


class SparkResultsToDatabase(ExternalTask):
    src = luigi.Parameter()
    date = luigi.DateParameter()
    dst = luigi.Parameter()

    def run(self):
        logger.info("Running HTTPRequestsToDB for date %s" % self.date)
        yield HTTPRequestsToDB(src=self.src, date=self.date, dst=self.dst)


def run(date_interval, src="s3n://ooni-public/reports-sanitised/streams/",
        dst="s3n://ooni-public/processed/", worker_processes=16):

    sch = luigi.scheduler.CentralPlannerScheduler()
    w = luigi.worker.Worker(
        scheduler=sch, worker_processes=worker_processes)

    imported_dates = get_imported_dates(
        src, aws_access_key_id=config.aws.access_key_id,
        aws_secret_access_key=config.aws.secret_access_key)

    interval = get_date_interval(date_interval)
    for date in interval:
        if str(date) not in imported_dates:
            continue

        logger.info("Running CountInterestingReports for %s on %s to %s" %
                    (date, src, dst))
        task = SparkResultsToDatabase(src=src, date=date, dst=dst)
        w.add(task)

    w.run()
    w.stop()
