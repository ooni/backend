from __future__ import absolute_import, print_function, unicode_literals

import os

from pipeline.helpers.binario import Emitter, Pipe
from pipeline.helpers.settings import config
from pipeline.helpers.s3 import S3Uploader


class LocalFileEmitter(Emitter):
    def filename_filter(self, filename):
        if filename.endswith(".yamloo"):
            return True
        return False

    def emit(self):
        for root, dirs, files in os.walk(config["raw_reports_dir"]):
            for filename in files:
                if self.filename_filter(filename):
                    yield os.path.join(root, filename)


class S3ReportUploadPipe(Pipe):
    def initialize(self):
        access_key_id = config["aws"]["access-key-id"]
        secret_access_key = config["aws"]["secret-access-key"]
        bucket_name = config["aws"]["s3-bucket-name"]
        self.s3_uploader = S3Uploader(access_key_id, secret_access_key,
                                      bucket_name)

    def process(self, source_path):
        bucket_name = config["aws"]["s3-bucket-name"]
        dst_path = os.path.join("new-reports", os.path.basename(source_path))
        self.log("Upload %s to %s" % (source_path, dst_path))
        self.s3_uploader.upload(bucket_name, source_path, dst_path)


local_file_emitter = LocalFileEmitter(1)
report_upload_pipe = S3ReportUploadPipe(24)

local_file_emitter.into(report_upload_pipe)

local_file_emitter.start()
