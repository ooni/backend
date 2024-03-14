from typing import Annotated
from clickhouse_driver import Client as ClickhouseClient
from fastapi import Depends

from .common.dependencies import get_settings
from .common.config import Settings


def get_clickhouse_client(
    settings: Annotated[Settings, Depends(get_settings)]
) -> ClickhouseClient:
    return ClickhouseClient.from_url(settings.clickhouse_url)
