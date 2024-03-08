from typing import Any, Dict, List
from sqlalchemy import create_engine, JSON
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import sessionmaker

from .config import settings

engine = create_engine(settings.postgresql_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    type_annotation_map = {
        Dict[str, Any]: JSON,
        List[Dict[str, Any]]: JSON,
        Dict[str, str]: JSON,
    }
