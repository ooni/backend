from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
from datetime import datetime

from .utils import ISO_TIMESTAMP_SHORT
from .database import Base

from sqlalchemy.orm import relationship

from sqlalchemy import (
    Column, Integer, String, Text,
    DateTime, Float, JSON, Numeric,
    ARRAY, Boolean,
    ForeignKey
)

from sqlalchemy.dialects.postgresql import (
    INET, ENUM, BYTEA, UUID
)

TEST_NAMES = {
    'web_connectivity': 'Web Connectivity',
    'http_requests': 'HTTP Requests',
    'dns_consistency': 'DNS Consistency',
    'http_invalid_request_line': 'HTTP Invalid Request Line',
    'bridge_reachability': 'Bridge Reachability',
    'tcp_connect': 'TCP Connect',
    'http_header_field_manipulation': 'HTTP Header Field Manipulation',
    'http_host': 'HTTP Host',
    'multi_protocol_traceroute': 'Multi Protocol Traceroute',
    'meek_fronted_requests_test': 'Meek Fronted Requests',
    'whatsapp': 'WhatsApp',
    'vanilla_tor': 'Vanilla Tor',
    'facebook_messenger': 'Facebook Messenger',
    'ndt': 'NDT'
}

# create domain size4 as int4 check (value >= 0);
SHA1 = BYTEA()

# create domain sha1 as bytea check (octet_length(value) = 20);
SIZE4 = Integer()

OOTEST = ENUM(
    *TEST_NAMES,
    name='ootest'
)

class Report(Base):
    __tablename__ = 'report'

    report_no = Column(Integer, primary_key=True)

    autoclaved_no = Column(Integer, ForeignKey('autoclaved.autoclaved_no'))
    autoclaved = relationship('Autoclaved', back_populates='reports')

    test_start_time = Column(DateTime)
    probe_cc = Column(String(2))
    probe_asn = Column(Integer)
    probe_ip = Column(INET)
    test_name = Column(OOTEST)
    badtail = Column(SIZE4)
    textname = Column(String)
    orig_sha1 = Column(SHA1)
    report_id = Column(String)
    software_no = Column(Integer,  ForeignKey('software.software_no'))
    software  = relationship('Software', back_populates='reports')

    measurements = relationship('Measurement', back_populates='report', lazy='dynamic')

class Autoclaved(Base):
    __tablename__ = 'autoclaved'

    autoclaved_no = Column(Integer, primary_key=True)
    reports = relationship('Report', back_populates='autoclaved')

    filename = Column(String)
    bucket_date = Column(DateTime)
    code_ver = Column(Integer)
    file_size = Column(SIZE4)
    file_crc32 = Column(Integer)
    file_sha1 = Column(SHA1)

class Measurement(Base):
    __tablename__ = 'measurement'

    msm_no = Column(Integer, primary_key=True)

    report_no = Column(Integer, ForeignKey('report.report_no'))
    report = relationship('Report', back_populates='measurements')

    frame_off = Column(SIZE4)
    frame_size = Column(SIZE4)
    intra_off = Column(SIZE4)
    intra_size = Column(SIZE4)

    measurement_start_time = Column(DateTime)
    test_runtime = Column(Float)
    orig_sha1 = Column(SHA1)
    id = Column(UUID)

    exc = Column(ARRAY(Integer))
    residual_no = Column(Integer)
    msm_failure = Column(Boolean)
    anomaly = Column(Boolean)
    confirmed = Column(Boolean)

    label = relationship('Label', back_populates='measurement')

    input_no = Column(Integer, ForeignKey('input.input_no'))
    input = relationship('Input', back_populates='measurements')

class Label(Base):
    """
    This table is used to manually markup or annotate measurements with some values.
    """
    __tablename__ = 'label'
    msm_no = Column(Integer, ForeignKey('measurement.msm_no'))
    measurement = relationship('Measurement', back_populates='label')

    msm_failure = Column(Boolean)
    anomaly = Column(Boolean)
    confirmed = Column(Boolean)

class Input(Base):
    __tablename__ = 'input'
    input_no = Column(Integer, primary_key=True)
    input = Column(String)

    measurements = relationship('Measurement', back_populates='input')

class Software(Base):
    __tablename__ = 'software'
    software_no = Column(Integer, primary_key=True)
    test_name = Column(String)
    test_version = Column(String)
    software_name = Column(String)
    software_version = Column(String)

    reports = relationship('Report', back_populates='software')
