from clickhouse_driver import Client as ClickhouseClient

from .config import settings


def get_clickhouse_client() -> ClickhouseClient:
    return ClickhouseClient.from_url(settings.clickhouse_url)
