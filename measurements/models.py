from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
from datetime import datetime

from .utils import ISO_TIMESTAMP_SHORT
from .database import Base
from sqlalchemy import (
    Column, Integer, String, Text,
    DateTime, Float, JSON,
)

# XXX rename to Base to create it in the database.
class Measurement(object):
    __tablename__ = 'measurements'

    id = Column(Text, primary_key=True)
    input = Column(Text)
    probe_asn = Column(String(200))
    probe_cc = Column(String(2))
    probe_ip = Column(String(200))
    software_name = Column(String(2000))
    software_version = Column(String(200))
    report_filename = Column(String(2000))
    report_id = Column(String(2000))
    test_start_time = Column(DateTime)
    test_runtime = Column(Float)
    measurement_start_time = Column(DateTime)
    test_name = Column(String(2000))
    data_format_version = Column(String(200))

    # These are commented out since we don't use this table and JSON is not
    #  a type supported by sqlite.
    # options = Column(JSON)
    # test_helpers = Column(JSON)
    # test_keys = Column(JSON)


class ReportFile(Base):
    __tablename__ = 'report_files'

    id = Column(Integer, primary_key=True, autoincrement=True)
    probe_asn = Column(String(200))
    probe_cc = Column(String(2))
    report_id = Column(String(2000))
    test_start_time = Column(DateTime)
    test_name = Column(String(2000))

    bucket_date = Column(String(200))

    filename = Column(String(2000))

    @staticmethod
    def from_filepath(file_path):
        dirname = os.path.basename(os.path.dirname(file_path))
        filename = os.path.basename(file_path)

        (test_start_time, probe_cc, probe_asn,
         test_name, report_id, _, _) = filename.split('-')
        report_file = ReportFile()
        report_file.test_start_time = datetime.strptime(test_start_time,
                                                        ISO_TIMESTAMP_SHORT)
        report_file.bucket_date = dirname
        report_file.probe_cc = probe_cc
        report_file.probe_asn = probe_asn
        report_file.test_name = test_name
        report_file.report_id = report_id
        report_file.filename = filename

        return report_file
