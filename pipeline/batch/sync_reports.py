import os
import shutil
import logging

import luigi
import luigi.worker

from invoke.config import Config

from pipeline.helpers.util import get_luigi_target, list_report_files

config = Config(runtime_path="invoke.yaml")
logger = logging.getLogger('ooni-pipeline')


class MoveReportFiles(luigi.Task):
    report_file = luigi.Parameter()
    dst_dir = luigi.Parameter()

    def input(self):
        return get_luigi_target(self.report_file,
            ssh_key_file=config.core.ssh_private_key_file,
            no_host_key_check=True)

    def output(self):
        dst_path = os.path.join(self.dst_dir,
                os.path.basename(self.report_file))
        return get_luigi_target(
            dst_path, ssh_key_file=config.core.ssh_private_key_file,
            no_host_key_check=True)

    def run(self):
        input = self.input()
        output = self.output()
        with output.open('w') as out_file:
            with input.open('r') as in_file:
                shutil.copyfileobj(in_file, out_file)
        input.remove()


def run(src_dir, dst_dir):
    sch = luigi.scheduler.CentralPlannerScheduler()
    w = luigi.worker.Worker(scheduler=sch)

    print(src_dir)

    for filename in list_report_files(
            src_dir, key_file=config.core.ssh_private_key_file,
            no_host_key_check=True):
        logging.info("moving %s to %s" % (filename, dst_dir))
        task = MoveReportFiles(report_file=filename, dst_dir=dst_dir)
        w.add(task, multiprocess=True)
    w.run()
