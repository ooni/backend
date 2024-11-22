from typing import Annotated

from clickhouse_driver import Client as Clickhouse

from fastapi import Depends

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .common.config import Settings
from .common.dependencies import get_settings


def get_postgresql_session(settings: Annotated[Settings, Depends(get_settings)]):
    engine = create_engine(settings.postgresql_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_clickhouse_session(settings: Annotated[Settings, Depends(get_settings)]):
    db = Clickhouse.from_url(settings.clickhouse_url)
    try:
        yield db
    finally:
        db.disconnect()
