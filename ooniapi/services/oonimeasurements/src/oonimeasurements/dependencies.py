from typing import Annotated

from fastapi import Depends

from sqlalchemy import create_engine
from clickhouse_sqlalchemy import make_session

from .common.config import Settings
from .common.dependencies import get_settings

def get_clickhouse_session(settings: Annotated[Settings, Depends(get_settings)]):
    engine = create_engine(settings.clickhouse_url)
    session = make_session(engine)
 
    try:
        yield session
    finally: 
        session.close()
