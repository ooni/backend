import logging
from datetime import datetime

import luigi
import luigi.worker
import luigi.postgres

from invoke.config import Config

from pipeline.helpers.util import json_loads, get_date_interval
from pipeline.helpers.util import get_imported_dates, json_dumps

from pipeline.batch.sanitise import AggregateYAMLReports

config = Config(runtime_path="invoke.yaml")
logger = logging.getLogger('ooni-pipeline')

class ReportHeadersToDatabase(luigi.postgres.CopyToTable):
    src = luigi.Parameter()
    dst_private = luigi.Parameter()
    dst_public = luigi.Parameter()

    date = luigi.DateParameter()

    host = str(config.postgres.host)
    database = str(config.postgres.database)
    user = str(config.postgres.username)
    password = str(config.postgres.password)
    table = str(config.postgres.table)

    columns = [
        ('input', 'TEXT'),
        ('report_id', 'TEXT'),
        ('report_filename', 'TEXT'),
        ('options', 'JSONB'),
        ('probe_cc', 'TEXT'),
        ('probe_asn', 'TEXT'),
        ('probe_ip', 'TEXT'),
        ('data_format_version', 'TEXT'),
        ('test_name', 'TEXT'),
        ('test_start_time', 'TIMESTAMP'),
        ('test_runtime', 'REAL'),
        ('test_helpers', 'JSONB'),
        ('test_keys', 'JSONB')
    ]

    def requires(self):
        return AggregateYAMLReports(dst_private=self.dst_private,
                                    dst_public=self.dst_public,
                                    src=self.src,
                                    date=self.date)

    def format_record(self, entry):
        record = []
        for (col_name, col_type) in self.columns:
            if col_name == 'test_keys': # this column gets a json_dump of whatever's left
                continue
            elif col_name == 'test_start_time': # Entry is actually called start_time
                start_time = entry.pop('start_time')
                test_start_time = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")
                record.append(test_start_time)
            elif col_type == 'JSONB':
                record.append(json_dumps(entry.pop(col_name, None)))
            elif col_type == 'INTEGER':
                try:
                    record.append(int(entry.pop(col_name)))
                except KeyError:
                    record.append(None)
            else:
                record.append(entry.pop(col_name, None))
        record.append(json_dumps(entry))
        return record

    def rows(self):
        sanitised_streams = self.input()["sanitised_streams"]
        with sanitised_streams.open('r') as in_file:
            for line in in_file:
                record = json_loads(line.strip('\n'))
                logger.info("Looking at %s with id %s" % (record["record_type"], record["report_id"]))
                if record["record_type"] == "entry":
                    logger.info("Found entry")
                    yield self.format_record(record)

def run(src, dst_private, dst_public, date_interval, worker_processes=16):
    sch = luigi.scheduler.CentralPlannerScheduler()
    w = luigi.worker.Worker(scheduler=sch,
                            worker_processes=worker_processes)

    imported_dates = get_imported_dates(src,
                                        aws_access_key_id=config.aws.access_key_id,
                                        aws_secret_access_key=config.aws.secret_access_key)
    interval = get_date_interval(date_interval)
    for date in interval:
        if str(date) not in imported_dates:
            continue
        logging.info("adding headers for date: %s" % date)
        task = ReportHeadersToDatabase(dst_private=dst_private,
                                       dst_public=dst_public,
                                       src=src, date=date)
        w.add(task, multiprocess=True)
    w.run()
