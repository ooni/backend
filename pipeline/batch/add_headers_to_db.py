import logging
import json

import luigi
import luigi.worker
import luigi.postgres

from invoke.config import Config

from pipeline.helpers.util import json_loads, get_date_interval, get_luigi_target
from pipeline.helpers.util import get_imported_dates, json_dumps
from pipeline.helpers.report import header_avro

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
        ('options', 'TEXT'),
        ('probe_cc', 'TEXT'),
        ('probe_asn', 'TEXT'),
        ('probe_ip', 'TEXT'),
        ('data_format_version', 'TEXT'),
        ('test_name', 'TEXT'),
        ('test_start_time', 'TEXT'),
        ('test_runtime', 'TEXT'),
        ('test_helpers', 'TEXT'),
        ('test_keys', 'JSON')
    ]

    def requires(self):
        return AggregateYAMLReports(dst_private=self.dst_private,
                                    dst_public=self.dst_public,
                                    src=self.src,
                                    date=self.date)

    def format_record(self, entry):
        base_keys = [
            'input',
            'report_id',
            'report_filename',
            'options',
            'probe_cc',
            'probe_asn',
            'probe_ip',
            'data_format_version',
            'test_name',
            'test_start_time',
            'test_runtime',
            'test_helpers'
        ]

        keys = [k for k in base_keys]
        record = []
        for k in keys:
            record.append(entry.pop(k, None))
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

#    imported_dates = get_imported_dates(src,
#                                        aws_access_key_id=config.aws.access_key_id,
#                                        aws_secret_access_key=config.aws.secret_access_key)
    interval = get_date_interval(date_interval)
    for date in interval:
#        if str(date) not in imported_dates:
#            continue
        logging.info("adding headers for date: %s" % date)
        task = ReportHeadersToDatabase(dst_private=dst_private,
                                       dst_public=dst_public,
                                       src=src, date=date)
        w.add(task, multiprocess=True)
    w.run()
