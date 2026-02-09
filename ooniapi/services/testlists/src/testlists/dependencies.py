from typing import Annotated, TypeAlias
from fastapi import Depends
from .common.config import Settings
from .common.dependencies import get_settings
from sqlalchemy.orm import sessionmaker
from clickhouse_driver import Client as Clickhouse
import boto3
from mypy_boto3_s3 import S3Client
from sqlalchemy import create_engine

SettingsDep: TypeAlias = Annotated[Settings, Depends(get_settings)]

def get_clickhouse_session(settings: SettingsDep):
    db = Clickhouse.from_url(settings.clickhouse_url)
    try:
        yield db
    finally:
        db.disconnect()


ClickhouseDep = Annotated[Clickhouse, Depends(get_clickhouse_session)]


def get_postgresql_session(settings: SettingsDep):
    engine = create_engine(settings.postgresql_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_s3_client() -> S3Client:
    s3 = boto3.client("s3")
    return s3


S3ClientDep = Annotated[S3Client, Depends(get_s3_client)]
