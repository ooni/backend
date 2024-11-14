from clickhouse_sqlalchemy import types
from sqlalchemy import Column

from .common.clickhouse import Base

class Fastpath(Base):
    __tablename__ = "fastpath"

    measurement_uid = Column(types.String)

    report_id = Column(types.types.String)
    input_ = Column('input', types.String)
    probe_cc = Column(types.String)
    probe_asn = Column(types.UInt32)
    test_name = Column(types.String)
    test_start_time = Column(types.DateTime)
    measurement_start_time = Column(types.DateTime)
    filename = Column(types.String)
    scores = Column(types.String)
    platform = Column(types.String)
    anomaly = Column(types.String)
    confirmed = Column(types.String)
    msm_failure = Column(types.String)
    domain = Column(types.String)
    software_name = Column(types.String)
    software_version = Column(types.String)
    control_failure = Column(types.String)
    blocking_general = Column(types.Float32)
    is_ssl_expected = Column(types.Int8)
    page_len = Column(types.Int32)
    page_len_ratio = Column(types.Float32)
    server_cc = Column(types.String)
    server_asn = Column(types.Int8)
    server_as_name = Column(types.String)
    update_time = Column(types.DateTime64(3))
    test_version = Column(types.String)
    test_runtime = Column(types.Float32)
    architecture = Column(types.String)
    engine_name = Column(types.String)
    engine_version = Column(types.String)
    blocking_type = Column(types.String)
    test_helper_address = Column(types.LowCardinality(types.String))
    test_helper_type = Column(types.LowCardinality(types.String))
    ooni_run_link_id = Column(types.UInt64, nullable=True)


class Jsonl(Base):
    __tablename__ = "jsonl"

    report_id = Column(types.String)                 
    input_ = Column('input', types.String)
    s3path = Column(types.String)       
    linenum = Column(types.Int32)             
    measurement_uid = Column(types.String)


class Citizenlab(Base):
    __tablename__ = "citizenlab"

    domain = Column(types.String)
    url = Column(types.String)
    cc = Column(types.String)
    category_code = Column(types.String)