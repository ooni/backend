from functools import lru_cache
from typing import Annotated

from fastapi import Depends

import geoip2.database

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .common.config import Settings
from .common.dependencies import get_settings


SettingsDep = Annotated[Settings, Depends(get_settings)]
def get_postgresql_session(settings: SettingsDep):
    engine = create_engine(settings.postgresql_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@lru_cache
def get_cc_reader(settings: SettingsDep):
    # TODO(luis) decide where to put the database within the filesystem
    db_path = ""
    reader = geoip2.database.Reader(db_path)
CCReaderDep = Annotated[geoip2.database.Reader, Depends(get_cc_reader)]

@lru_cache
def get_asn_reader(settings: SettingsDep):
    # TODO(luis) decide where to put the database within the filesystem
    db_path = ""
    reader = geoip2.database.Reader(db_path)
ASNReaderDep = Annotated[geoip2.database.Reader, Depends(get_asn_reader)]