import statsd

from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "OONI Data API"
    base_url: str = "https://api.ooni.io"
    clickhouse_url: str = "clickhouse://localhost"
    log_level: str = "info"
    s3_bucket_name: str = "oonidata-eufra"
    other_collectors: List[str] = []
    statsd_host = "localhost"
    statsd_port = 8125
    statsd_prefix = "ooniapi"


settings = Settings()
metrics = statsd.StatsClient(
    settings.statsd_host, settings.statsd_port, prefix=settings.statsd_prefix
)
