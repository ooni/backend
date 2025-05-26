from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

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

DependsPostgresSession = Annotated[Session, Depends(get_postgresql_session)]