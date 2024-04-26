from typing import Annotated

from fastapi import Depends

from clickhouse_driver import Client as Clickhouse

from .common.config import Settings
from .common.dependencies import get_settings

def get_clickhouse_session(settings: Annotated[Settings, Depends(get_settings)]):
    db = Clickhouse.from_url(settings.clickhouse_url)
    try:
        yield db
    finally: 
        db.disconnect_connection()
