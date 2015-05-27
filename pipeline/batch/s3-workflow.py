import shutil

import luigi
import luigi.worker
import luigi.hdfs
from luigi.task import ExternalTask
from luigi.format import GzipFormat
from luigi.s3 import S3Target
from luigi.configuration import get_config


def list_raw_reports():
    config = get_config()
    from boto.s3.connection import S3Connection

    AWS_ACCESS_KEY_ID = config.get('aws', 'access-key-id')
    AWS_SECRET_ACCESS_KEY = config.get('aws', 'secret-access-key')

    S3_BUCKET_NAME = config.get('aws', 's3-bucket-name')

    con = S3Connection(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    bucket = con.get_bucket(S3_BUCKET_NAME)
    keys = bucket.list('reports')
    for key in keys:
        yield (S3_BUCKET_NAME, key.name)


class S3GzipTask(ExternalTask):
    path = luigi.Parameter()

    def output(self):
        return S3Target(self.path, format=GzipFormat())


class S3RawReportsRenameUncompress(luigi.Task):
    bucket = luigi.Parameter()
    filename = luigi.Parameter()

    def get_uri(self):
        return "s3n://%s/%s" % (self.bucket, self.filename)

    def requires(self):
        return S3GzipTask(self.get_uri())

    def output(self):
        parts = self.filename.replace("reports/", "").split("-")
        date = '-'.join(parts[-5:-2])
        asn = parts[-2]
        ext = parts[-1].replace(".gz", "")
        test_name = '-'.join(parts[:-5])
        filename = "%s-%s-%s-%s" % (date, asn, test_name, ext)
        uri = "s3n://%s/uncompressed/%s" % (self.bucket, filename)
        return S3Target(uri)

    def run(self):
        with self.input().open('r') as in_file:
            with self.output().open('w') as out_file:
                shutil.copyfileobj(in_file, out_file)

if __name__ == "__main__":
    luigi.interface.setup_interface_logging()
    sch = luigi.scheduler.CentralPlannerScheduler()
    tasks = []
    worker_processes = 16
    idx = 0
    w = luigi.worker.Worker(scheduler=sch,
                            worker_processes=worker_processes)

    for bucket, filename in list_raw_reports():
        print "Working on %s" % filename
        task = S3RawReportsRenameUncompress(bucket=bucket,
                                            filename=filename)
        w.add(task)
        idx += 1
    w.run()
    w.stop()
