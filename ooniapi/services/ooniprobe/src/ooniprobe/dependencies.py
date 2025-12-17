import io
from functools import lru_cache
from pathlib import Path
from typing import Annotated, TypeAlias, Dict, Any

import boto3
import geoip2.database
from clickhouse_driver import Client as Clickhouse
from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from mypy_boto3_s3 import S3Client

from .common.config import Settings
from .common.dependencies import get_settings


SettingsDep: TypeAlias = Annotated[Settings, Depends(get_settings)]


def get_postgresql_session(settings: SettingsDep):
    engine = create_engine(settings.postgresql_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_cc_reader(settings: SettingsDep):
    db_path = Path(settings.geoip_db_dir, "cc.mmdb")
    return geoip2.database.Reader(db_path)


CCReaderDep = Annotated[geoip2.database.Reader, Depends(get_cc_reader)]


def get_asn_reader(settings: SettingsDep):
    db_path = Path(settings.geoip_db_dir, "asn.mmdb")
    return geoip2.database.Reader(db_path)


ASNReaderDep = Annotated[geoip2.database.Reader, Depends(get_asn_reader)]


def get_clickhouse_session(settings: SettingsDep):
    db = Clickhouse.from_url(settings.clickhouse_url)
    try:
        yield db
    finally:
        db.disconnect()


ClickhouseDep = Annotated[Clickhouse, Depends(get_clickhouse_session)]


def get_s3_client() -> S3Client:
    s3 = boto3.client("s3")
    return s3


S3ClientDep = Annotated[S3Client, Depends(get_s3_client)]


@lru_cache
def read_file(s3_client : S3ClientDep, bucket: str, file : str) -> str:
    """
    Reads the content of `file` within `bucket` into a  string

    Useful for reading config files from the s3 bucket
    """
    buff = io.BytesIO()
    s3_client.download_fileobj(bucket, file, buff)
    return buff.getvalue().decode()


async def get_tor_targets_from_s3(settings: SettingsDep, s3client: S3ClientDep) -> Dict[str, Any]:
    with read_file(s3client, settings.config_bucket, settings.tor_targets) as f:
        resp = ujson.load(f)
    yield resp

TorTargetsDep = Annotated[Dict, Depends(get_tor_targets_from_s3)]
