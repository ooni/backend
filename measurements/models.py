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
    DateTime, Float, JSON, Numeric
)

from sqlalchemy.dialects.postgresql import (
    INET, ENUM, BYTEA
)

# create domain size4 as int4 check (value >= 0);
SHA1 = BYTEA()

# create domain sha1 as bytea check (octet_length(value) = 20);
SIZE4 = Integer()

OOTEST = ENUM(
    'web_connectivity',
    'http_requests',
    'dns_consistency',
    'http_invalid_request_line',
    'bridge_reachability',
    'tcp_connect',
    'http_header_field_manipulation',
    'http_host',
    'multi_protocol_traceroute',
    'meek_fronted_requests_test',
    'whatsapp',
    'vanilla_tor',
    'facebook_messenger',
    'ndt',
    name='ootest'
)

# XXX adjust the offset to be the maximum index in the database at migration time
REPORT_INDEX_OFFSET = 1000

class Report(Base):
    __tablename__ = 'report'

    report_no = Column(Integer, primary_key=True)
    autoclaved_no = Column(Integer) # Foreign key REFERENCES autoclaved (autoclaved_no)
    test_start_time = Column(DateTime)
    probe_cc = Column(String(2))
    probe_asn = Column(Integer)
    probe_ip = Column(INET)
    test_name = Column(OOTEST)
    badtail = Column(SIZE4)
    textname = Column(String)
    orig_sha1 = Column(SHA1)
    report_id = Column(String)
    software_no = Column(Integer)

class ReportFile(Base):
    __tablename__ = 'report_files'

    id = Column(Integer, primary_key=True, autoincrement=True)
    probe_asn = Column(String(200))
    probe_cc = Column(String(2))
    report_id = Column(String(2000))
    test_start_time = Column(DateTime)
    test_name = Column(String(2000))

    # Idx is a unique identifier of a certain report_file. This allows
    # retrieving only report files from a given offset.
    idx = Column(Numeric)
    bucket_date = Column(String(200))

    filename = Column(String(2000))

    @staticmethod
    def from_filepath(file_path, index):
        dirname = os.path.basename(os.path.dirname(file_path))
        filename = os.path.basename(file_path)

        (test_start_time, probe_cc, probe_asn,
         test_name, report_id, _, _) = filename.split('-')

        report_file = ReportFile()
        report_file.test_start_time = datetime.strptime(test_start_time,
                                                        ISO_TIMESTAMP_SHORT)

        report_file.idx = index
        report_file.bucket_date = dirname

        report_file.probe_cc = probe_cc
        report_file.probe_asn = probe_asn
        report_file.test_name = test_name
        report_file.report_id = report_id
        report_file.filename = filename

        return report_file
