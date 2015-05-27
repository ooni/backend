from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime


Base = declarative_base()


class ReportHeader(Base):
    __tablename__ = "reports"

    report_id = Column(String(64))
    probe_asn = Column(String(16))
    software_name = Column(String(128))
    software_version = Column(String(16))
    start_time = Column(DateTime())
    test_name = Column(String(128))
    test_version = Column(String(16))
    measurement_count = Column(Integer())

    # Optional
    data_format_version = Column(String(16))
    test_helpers = Column(String())
    options = Column(String())
    probe_ip = Column(String(128))
