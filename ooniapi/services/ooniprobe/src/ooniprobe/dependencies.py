from typing import Annotated, TypeAlias
from pathlib import Path

from fastapi import Depends

import geoip2.database

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from clickhouse_driver import Client as Clickhouse

from .common.config import Settings
from .common.dependencies import get_settings


SettingsDep : TypeAlias = Annotated[Settings, Depends(get_settings)]

def get_postgresql_session(settings: SettingsDep):
    engine = create_engine(settings.postgresql_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_cc_reader(settings: SettingsDep):
    # TODO(luis) decide where to put the database within the filesystem
    db_path = Path(settings.geoip_db_dir, "cc.mmdb")
    reader = geoip2.database.Reader(db_path)
CCReaderDep = Annotated[geoip2.database.Reader, Depends(get_cc_reader)]

def get_asn_reader(settings: SettingsDep):
    # TODO(luis) decide where to put the database within the filesystem
    db_path = Path(settings.geoip_db_dir, "asn.mmdb")
    reader = geoip2.database.Reader(db_path)
ASNReaderDep = Annotated[geoip2.database.Reader, Depends(get_asn_reader)]


def get_clickhouse_session(settings: SettingsDep):
    db = Clickhouse.from_url(settings.clickhouse_url)
    try:
        yield db
    finally:
        db.disconnect()

ClickhouseDep = Annotated[Clickhouse, Depends(get_clickhouse_session)]