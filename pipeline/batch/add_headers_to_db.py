import logging
import json

import luigi
import luigi.worker
import luigi.postgres

from invoke.config import Config

from pipeline.helpers.util import json_loads, get_date_interval, get_luigi_target
from pipeline.helpers.util import get_imported_dates
from pipeline.helpers.report import header_avro

from pipeline.batch.sanitise import AggregateYAMLReports

config = Config(runtime_path="invoke.yaml")
logger = logging.getLogger('ooni-pipeline')

columns = []
for field in header_avro["fields"]:
    if field["type"] == "string":
        columns.append((field["name"], "TEXT"))
    elif field["type"] == "array":
        columns.append((field["name"], "TEXT"))
    elif field["type"] == "float":
        columns.append((field["name"], "FLOAT"))

class ReportHeadersToDatabase(luigi.postgres.CopyToTable):
    src = luigi.Parameter()
    dst_private = luigi.Parameter()
    dst_public = luigi.Parameter()
    bridge_db_path = luigi.Parameter()

    date = luigi.DateParameter()

    host = str(config.postgres.host)
    database = str(config.postgres.database)
    user = str(config.postgres.username)
    password = str(config.postgres.password)
    table = str(config.postgres.table)

    columns = columns

    def requires(self):
        with get_luigi_target(self.bridge_db_path).open('r') as f:
            bridge_db = json.load(f)
        return AggregateYAMLReports(dst_private=self.dst_private,
                                    dst_public=self.dst_public,
                                    src=self.src,
                                    date=self.date,
                                    bridge_db=bridge_db)

    def format_record(self, record):
        fields = []
        for field in header_avro["fields"]:
            if field["type"] == "string":
                fields.append(str(record.get(field["name"], "")))
            elif field["type"] == "array":
                fields.append(str(record.get(field["name"], "")))
            elif field["type"] == "float":
                fields.append(float(record.get(field["name"], 0)))
        return fields

    def rows(self):
        sanitised_streams = self.input()["sanitised_streams"]
        with sanitised_streams.open('r') as in_file:
            for line in in_file:
                record = json_loads(line.strip('\n'))
                logger.info("Looking at %s with id %s" % (record["record_type"], record["report_id"]))
                if record["record_type"] == "header":
                    logger.info("Found header")
                    yield self.format_record(record)

def run(src, dst_private, dst_public, date_interval, bridge_db_path,
        worker_processes=16):
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
                                       src=src, date=date,
                                       bridge_db_path=bridge_db_path)
        w.add(task)
    w.run()
    w.stop()
