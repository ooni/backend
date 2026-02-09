from typing import Dict, List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "OONI Data API"
    base_url: str = "https://api.ooni.io"
    clickhouse_url: str = "clickhouse://localhost"
    valkey_url: str = "valkey://localhost:6379"
    postgresql_url: str = "postgresql://oonidb:oonidb@localhost/oonidb"
    log_level: str = "info"
    # Prod bucket: "ooni-data-eu-fra"
    s3_bucket_name: str = "ooni-data-eu-fra-test"
    other_collectors: List[str] = []
    statsd_host: str = "localhost"
    statsd_port: int = 8125
    statsd_prefix: str = "ooniapi"
    jwt_encryption_key: str = "CHANGEME"
    prometheus_metrics_password: str = "CHANGEME"
    account_id_hashing_key: str = "CHANGEME"
    collector_id: str = "CHANGEME"
    session_expiry_days: int = 10
    login_expiry_days: int = 10
    rate_limits: str = "10/minute;400000/day;200000/7day"
    rate_limits_whitelisted_ipaddrs: List[str] = []
    rate_limits_unmetered_pages: List[str] = []

    admin_emails: List[str] = [
        "admin@ooni.org",
        "contact@ooni.org",
    ]

    aws_region: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    email_source_address: str = "contact+dev@ooni.io"

    vpn_credential_refresh_hours: int = 24

    # Bucket used to store configuration files
    config_bucket: str = ""

    # Where the geoip DBs are downloaded to
    geoip_db_dir: str = "/var/lib/ooni/geoip"
    # -- < Ooniprobe only > -------------------------------------------------------------
    msmt_spool_dir: str = ""
    fastpath_url: str = ""  # example: http://123.123.123.123:8472
    failed_reports_bucket: str = (
        ""  # for uploading reports that couldn't be sent to fastpath
    )
    tor_targets: str = (
        ""  # filename of json containing Tor bridges and DirAuth endpoints
    )

    # Used to store history of all manifests and retrieve next manifest to use
    anonc_manifest_bucket: str = Field(
        default="CHANGEME",
        description="Name of public bucket where anonymous credentials manifests are stored",
    )
    anonc_manifest_file: str = Field(
        default="CHANGEME",
        description="Name of the manifest file within the public bucket to use for ZKP verification",
    )
    anonc_secret_key: str = Field(
        default="CHANGEME",
        description="Secret key matching the specified manifest file",
    )

    # ooniprobe client configuration
    collectors: List[Dict[str, str]] = [
        {"address": "httpo://guegdifjy7bjpequ.onion", "type": "onion"},
        {"address": "https://ams-pg.ooni.org:443", "type": "https"},
        {
            "address": "https://dkyhjv0wpi2dk.cloudfront.net",
            "front": "dkyhjv0wpi2dk.cloudfront.net",
            "type": "cloudfront",
        },
        {"address": "httpo://guegdifjy7bjpequ.onion", "type": "onion"},
        {"address": "https://ams-pg.ooni.org:443", "type": "https"},
        {
            "address": "https://dkyhjv0wpi2dk.cloudfront.net",
            "front": "dkyhjv0wpi2dk.cloudfront.net",
            "type": "cloudfront",
        },
    ]

    # citizenlab github configuration
    working_dir: str = ""
    github_user: str = ""
    github_token: str = ""
    origin_repo: str = ""
    push_repo: str = ""
