from typing import Annotated

from fastapi import Depends

from clickhouse_driver import Client as Clickhouse

from .common.config import Settings
from .common.dependencies import get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]

def get_clickhouse_session(settings: SettingsDep):
    db = Clickhouse.from_url(settings.clickhouse_url)
    try:
        yield db
    finally:
        db.disconnect()

ClickhouseDep = Annotated[Clickhouse, Depends(get_clickhouse_session)]