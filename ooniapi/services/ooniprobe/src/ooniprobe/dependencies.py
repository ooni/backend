from typing import Annotated, TypeAlias
from pathlib import Path

from fastapi import Depends

import geoip2.database

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from clickhouse_driver import Client as Clickhouse

import boto3
from mypy_boto3_s3 import S3Client

from .common.config import Settings
from .common.dependencies import get_settings
from .models import OONIProbeServerState, OONIProbeManifest


SettingsDep: TypeAlias = Annotated[Settings, Depends(get_settings)]


def get_postgresql_session(settings: SettingsDep):
    engine = create_engine(settings.postgresql_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

PostgresSessionDep = Annotated[Session, Depends(get_postgresql_session)]

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


def get_latest_manifest(session : PostgresSessionDep) -> OONIProbeManifest:
    manifest = OONIProbeManifest.get_latest(session)
    assert manifest is not None, "Uninitialized `OONIProbeServerState` table"
    return manifest

LatestManifestDep = Annotated[OONIProbeManifest, Depends(get_latest_manifest)]