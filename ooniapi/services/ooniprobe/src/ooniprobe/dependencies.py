from typing import Annotated, Tuple, TypeAlias, Any, Dict
from datetime import datetime
import time
from pathlib import Path

from fastapi import Depends

import geoip2.database

import ujson
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from clickhouse_driver import Client as Clickhouse

import boto3
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


class Manifest(BaseModel):
    """
    Manifest used for ZKP verification
    """
    nym_scope: str = "ooni.org/{probe_cc}/{probe_asn}"
    submission_policy: Dict[str, Any] = dict()
    public_parameters: str

class ManifestMeta(BaseModel):
    """
    Manifest metadata
    """
    version: str
    last_modification_date: datetime
    manifest_url: str = Field(description="URL pointing to the AWS public record of this manifest")


def get_manifest(s3: S3ClientDep, bucket : str, file : str) -> Tuple[Manifest, ManifestMeta]:

    # Get version & metadata
    resp = s3.list_object_versions(
        Bucket=bucket,
        Prefix=file # Only get versions of the specified file
        )

    versions = resp.get("Versions")
    assert versions, "Couldn't find versions for the specified manifest"

    latest = next((x for x in versions if x.get('IsLatest')), None)

    assert latest, "Couldn't find latest manifest version. Is versioning activated?"
    assert 'VersionId' in latest, "Manifest version not provided"
    assert 'LastModified' in latest, "Last modification date not provided"

    meta = ManifestMeta(
        version=latest['VersionId'],
        last_modification_date=latest['LastModified'],
        manifest_url=f"https://{bucket}.s3.amazonaws.com/{file}",
        )

    # Get Object
    manifest_resp = s3.get_object(Bucket=bucket, Key=file)
    manifest_json = ujson.load(manifest_resp['Body'])

    return Manifest(**manifest_json), meta

__cache__ = dict()

def _get_manifest(s3: S3ClientDep, settings: SettingsDep) -> Tuple[Manifest, ManifestMeta]:
    key = (settings.anonc_manifest_bucket, settings.anonc_manifest_file)

    tup = __cache__.get(key)
    now = time.time()
    if tup is None or (tup[1] - now) > 60: # Non-existent or older than one minute
        val, _ = __cache__[key] = (get_manifest(s3, settings.anonc_manifest_bucket, settings.anonc_manifest_file), time.time())

    return val


LatestManifestDep = Annotated[Manifest, Depends(_get_manifest)]
