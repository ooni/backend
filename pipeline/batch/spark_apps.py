# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals

import os
import logging

import luigi
from luigi.contrib.spark import PySparkTask

from invoke.config import Config

from pipeline.helpers.util import get_luigi_target, json_dumps

config = Config(runtime_path="invoke.yaml")
logger = logging.getLogger('ooni-pipeline')


class CountInterestingReports(PySparkTask):
    driver_memory = '2g'
    executor_memory = '3g'

    files = luigi.Parameter()
    src = luigi.Parameter()

    def input(self):
        input_path = os.path.join(self.src, "reports-sanitised", "streams", self.files)
        return get_luigi_target(input_path)

    def output(self):
        output_path = os.path.join(self.src,
                                   "analysis",
                                   "http_requests_test-interesting-%s-done" % self.files)
        return get_luigi_target(output_path)

    def main(self, sc, *args):
        df = sc.jsonFile(self.input().path)
        http_requests = df.filter("test_name = 'http_requests_test' AND record_type = 'entry'")
        interestings = http_requests.filter("body_length_match = false OR headers_match = false").groupBy("report_id")
        for interesting in interestings.count().collect():
            output_file = os.path.join("s3://ooni-public/analysis/",
                                    "http_requests_test"
                                    "-interesting-" +
                                    interesting.report_id +
                                    "-count.json")
            t = get_luigi_target(output_file)
            with t.open('w') as out_file:
                data = json_dumps({
                    "report_id": interesting.report_id,
                    "count": interesting.count
                })
                out_file.write(data)
                out_file.write("\n")


def run(files="2013-12-25", src="s3n://ooni-public/", worker_processes=16):
    logger.info("Running CountInterestingReports for %s on %s" % (files, src))
    sch = luigi.scheduler.CentralPlannerScheduler()
    w = luigi.worker.Worker(scheduler=sch,
                            worker_processes=worker_processes)
    task = CountInterestingReports(src=src, files=files)
    w.add(task)
    w.run()
    w.stop()
