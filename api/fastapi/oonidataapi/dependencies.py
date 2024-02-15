from typing import Generator
from sqlalchemy.orm.session import Session

from clickhouse_driver import Client as ClickhouseClient
from .postgresql import SessionLocal

from .config import settings


def get_clickhouse_client() -> ClickhouseClient:
    return ClickhouseClient.from_url(settings.clickhouse_url)


def get_postgresql_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
