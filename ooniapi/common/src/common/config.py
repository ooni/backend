from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "OONI Data API"
    base_url: str = "https://api.ooni.io"
    clickhouse_url: str = "clickhouse://localhost"
    # In production you want to set this to: postgresql://user:password@postgresserver/db
    postgresql_url: str = "sqlite:///./testdb.sqlite3"
    log_level: str = "info"
    s3_bucket_name: str = "oonidata-eufra"
    other_collectors: List[str] = []
    statsd_host: str = "localhost"
    statsd_port: int = 8125
    statsd_prefix: str = "ooniapi"
    jwt_encryption_key: str = "CHANGEME"
    prometheus_metrics_password: str = "CHANGEME"
    session_expiry_days: int = 10
    login_expiry_days: int = 10
