from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "OONI Data API"
    base_url: str = "https://api.ooni.io"
    clickhouse_url: str = "clickhouse://localhost"
    postgresql_url: str = "postgresql://oonidb:oonidb@localhost/oonidb"
    log_level: str = "info"
    s3_bucket_name: str = "oonidata-eufra"
    other_collectors: List[str] = []
    statsd_host: str = "localhost"
    statsd_port: int = 8125
    statsd_prefix: str = "ooniapi"
    jwt_encryption_key: str = "CHANGEME"
    prometheus_metrics_password: str = "CHANGEME"
    account_id_hashing_key: str = "CHANGEME"
    session_expiry_days: int = 10
    login_expiry_days: int = 10

    admin_emails: List[str] = [
        "admin@ooni.org",
        "contact@ooni.org",
    ]

    aws_region: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    email_source_address: str = "contact+dev@ooni.io"
