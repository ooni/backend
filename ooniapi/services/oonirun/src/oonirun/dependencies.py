from typing import Annotated

from fastapi import Depends

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from clickhouse_driver import Client as Clickhouse

from .common.config import Settings
from .common.dependencies import get_settings


DependsSettings = Annotated[Settings, Depends(get_settings)]

def get_postgresql_session(settings: DependsSettings):
    engine = create_engine(settings.postgresql_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

DependsPostgresSession = Annotated[Session, Depends(get_postgresql_session)]

def get_clickhouse_session(settings: DependsSettings):
    db = Clickhouse.from_url(settings.clickhouse_url)
    try:
        yield db
    finally:
        db.disconnect()

DependsClickhouseSession = Annotated[Clickhouse, Depends(get_clickhouse_session)]