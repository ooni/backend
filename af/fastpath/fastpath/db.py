"""
OONI Fastpath

Database connector

See ../../oometa/017-fastpath.install.sql for the tables structure

"""

from datetime import datetime
from textwrap import dedent
from typing import Optional
from urllib.parse import urlparse
import logging

try:
    # debdeps: python3-clickhouse-driver
    from clickhouse_driver import Client as Clickhouse
except ImportError:
    pass
import ujson

from fastpath.metrics import setup_metrics
from fastpath.core import g_or as dget_or
from fastpath.core import g as dget_n

log = logging.getLogger("fastpath.db")
metrics = setup_metrics(name="fastpath.db")

click_client: Clickhouse


def extract_input_domain(msm: dict, test_name: str) -> tuple[str, str]:
    """Extract domain and handle special case meek_fronted_requests_test"""
    input_ = msm.get("input") or ""
    if test_name == "meek_fronted_requests_test" and isinstance(input_, list):
        domain = input_[0]  # type: str
        input_ = ",".join(input_)
        input_ = "{" + input_ + "}"
    else:
        assert isinstance(input_, str)
        domain = urlparse(input_).netloc
    return input_, domain


def _click_create_table_fastpath():
    # TODO: table creation should be done before starting workers
    sql = """
    CREATE TABLE IF NOT EXISTS fastpath
    (
        `measurement_uid` String,
        `report_id` String,
        `input` String,
        `probe_cc` String,
        `probe_asn` Int32,
        `test_name` String,
        `test_start_time` DateTime,
        `measurement_start_time` DateTime,
        `filename` String,
        `scores` String,
        `platform` String,
        `anomaly` String,
        `confirmed` String,
        `msm_failure` String,
        `domain` String,
        `software_name` String,
        `software_version` String,
        `control_failure` String,
        `blocking_general` Float32,
        `is_ssl_expected` Int8,
        `page_len` Int32,
        `page_len_ratio` Float32,
        `server_cc` String,
        `server_asn` Int8,
        `server_as_name` String
    )
    ENGINE = ReplacingMergeTree
    ORDER BY (measurement_start_time, report_id, input)
    SETTINGS index_granularity = 8192;
    """
    rows = click_client.execute(sql)
    log.debug(list(rows))


def click_create_table_obs_openvpn():
    sql = """
    CREATE TABLE IF NOT EXISTS obs_openvpn
    (
        anomaly Bool,
        bootstrap_time Float32,
        confirmed Bool,
        error String,
        failure Bool,
        input String,
        measurement_start_time DateTime,
        measurement_uid String,
        obfuscation String,
        platform String,
        probe_asn Int32,
        probe_cc String,
        probe_network_name String,
        provider String,
        remote String,
        report_id String,
        resolver_asn Int32,
        resolver_ip String,
        resolver_network_name String,
        software_name String,
        software_version String,
        success Bool,
        tcp_connect_status_success Bool,
        test_runtime Float32,
        test_start_time DateTime,
        transport String
    )
    ENGINE = ReplacingMergeTree
    ORDER BY (measurement_start_time, report_id, input)
    SETTINGS index_granularity = 8;
    """
    rows = click_client.execute(sql)
    log.debug(list(rows))


def setup_clickhouse(conf) -> None:
    global click_client
    log.info("Connecting to clickhouse")
    click_client = Clickhouse.from_url(conf.clickhouse_url)
    rows = click_client.execute("SELECT version()")
    log.debug(f"Clickhouse version: {rows[0][0]}")
    _click_create_table_fastpath()


@metrics.timer("clickhouse_upsert_summary")
def clickhouse_upsert_summary(
    msm,
    scores,
    anomaly: bool,
    confirmed: bool,
    msm_failure: bool,
    measurement_uid: str,
    software_name: str,
    software_version: str,
    platform: str,
) -> None:
    """Insert a row in the fastpath table. Overwrite an existing one."""
    sql_insert = dedent(
        """\
    INSERT INTO fastpath (
    measurement_uid,
    report_id,
    input,
    probe_cc,
    probe_asn,
    test_name,
    test_start_time,
    measurement_start_time,
    scores,
    platform,
    anomaly,
    confirmed,
    msm_failure,
    domain,
    software_name,
    software_version
    ) VALUES
        """
    )

    def nn(features: dict, k: str) -> str:
        """Get string value and never return None"""
        v = features.get(k, None)
        if v is None:
            return ""
        return v

    def tf(v: bool) -> str:
        return "t" if v else "f"

    test_name = msm.get("test_name", None) or ""
    input_, domain = extract_input_domain(msm, test_name)
    asn = int(msm["probe_asn"][2:])  # AS123
    measurement_start_time = datetime.strptime(
        msm["measurement_start_time"], "%Y-%m-%d %H:%M:%S"
    )
    test_start_time = datetime.strptime(msm["test_start_time"], "%Y-%m-%d %H:%M:%S")
    row = [
        measurement_uid,
        nn(msm, "report_id"),
        input_,
        nn(msm, "probe_cc"),
        asn,
        test_name,
        test_start_time,
        measurement_start_time,
        ujson.dumps(scores),
        nn(msm, "platform"),
        tf(anomaly),
        tf(confirmed),
        tf(msm_failure),
        domain,
        nn(msm, "software_name"),
        nn(msm, "software_version"),
    ]

    settings = {"priority": 5}
    try:
        click_client.execute(sql_insert, [row], settings=settings)
    except Exception:
        log.error("Failed Clickhouse insert", exc_info=True)

    # Future feature extraction:
    # def getint(features: dict, k: str, default: int) -> int:
    #     v = features.get(k, None)
    #     if v is None:
    #         v = default
    #     return v
    # get(features, "control_failure", ""),
    # getint(features, "is_ssl_expected", 2),
    # getint(features, "page_len", 0),
    # getint(features, "page_len_ratio", 0),
    # get(features, "server_cc", ""),
    # getint(features, "server_asn", 0),
    # get(features, "server_as_name", ""),
    # if "is_ssl_expected" in features:
    #     if features["is_ssl_expected"]:
    #         is_ssl_expected = "1"
    #     else:
    #         is_ssl_expected = "0"
    # else:
    #     is_ssl_expected = "2"


@metrics.timer("clickhouse_upsert_openvpn_obs")
def clickhouse_upsert_openvpn_obs(
    msm,
    scores,
    measurement_uid: str,
) -> None:
    sql_insert = dedent(
        """\
    INSERT INTO obs_openvpn (
    anomaly,
    bootstrap_time,
    confirmed,
    error,
    failure,
    input,
    measurement_start_time,
    measurement_uid,
    obfuscation,
    platform,
    probe_asn,
    probe_cc,
    probe_network_name,
    provider,
    remote,
    report_id,
    resolver_asn,
    resolver_ip,
    resolver_network_name,
    software_name,
    software_version,
    success,
    tcp_connect_status_success,
    test_runtime,
    test_start_time,
    transport
    ) VALUES
        """
    )

    def nn(d: dict, k: str) -> str:
        """Get string value and never return None"""
        v = d.get(k)
        return "" if v is None else v

    def tf(v: bool) -> str:
        return "t" if v else "f"

    asn = int(msm["probe_asn"][2:])  # AS123
    measurement_start_time = datetime.strptime(
        msm["measurement_start_time"], "%Y-%m-%d %H:%M:%S"
    )
    test_start_time = datetime.strptime(msm["test_start_time"], "%Y-%m-%d %H:%M:%S")
    tk = dget_or(msm, "test_keys", {})

    anomaly = nn(msm, "success") == True
    tcp_connect_status_success = "t" #FIXME
    row = dict(
      anomaly = anomaly,
      bootstrap_time = dget_or(tk, "bootstrap_time", 0),
      confirmed = "f",
      error = nn(msm, "error"),
      failure = nn(msm, "failure"),
      input = nn(msm, "input"),
      measurement_start_time = measurement_start_time,
      measurement_uid = measurement_uid,
      obfuscation = nn(tk, "obfuscation"),
      platform = nn(msm, "platform"),
      probe_asn = asn,
      probe_cc = nn(msm, "probe_cc"),
      probe_network_name = nn(msm, "probe_network_name"),
      provider = nn(tk, "provider"),
      remote = nn(tk, "remote"),
      report_id = nn(msm, "report_id"),
      resolver_asn = nn(msm, "resolver_asn"),
      resolver_ip = nn(msm, "resolver_ip"),
      resolver_network_name = nn(msm, "resolver_network_name"),
      software_name = nn(msm, "software_name"),
      software_version = nn(msm, "software_version"),
      success = nn(msm, "success"),
      tcp_connect_status_success = tcp_connect_status_success,
      test_runtime = dget_or(msm, "test_runtime", 0),
      test_start_time = test_start_time,
      transport = nn(tk, "transport")
    )

    settings = {"priority": 5}
    try:
        click_client.execute(sql_insert, [row], settings=settings)
    except Exception:
        log.error("Failed Clickhouse insert", exc_info=True)
