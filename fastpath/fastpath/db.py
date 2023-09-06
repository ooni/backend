"""
OONI Fastpath

Database connector

See ../../oometa/017-fastpath.install.sql for the tables structure

"""

from datetime import datetime
from textwrap import dedent
from urllib.parse import urlparse
from typing import List, Tuple, Dict
import logging

try:
    # debdeps: python3-clickhouse-driver
    from clickhouse_driver import Client as Clickhouse
except ImportError:
    pass
import ujson

from fastpath.metrics import setup_metrics
from fastpath.utils import dget_or

log = logging.getLogger("fastpath.db")
metrics = setup_metrics(name="fastpath.db")

click_client: Clickhouse
fastpath_row_buffer = []


def extract_input_domain(msm: dict, test_name: str) -> Tuple[str, str]:
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


def _click_create_table_fastpath() -> None:
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
        `server_as_name` String,
        `blocking_type` String,
        `test_version` String,
        `test_runtime` Float32,
        `architecture` String,
        `engine_name` String,
        `engine_version` String,
        `test_helper_address` String,
        `test_helper_type` String
    )
    ENGINE = ReplacingMergeTree
    ORDER BY (measurement_start_time, report_id, input)
    SETTINGS index_granularity = 8192;
    """
    rows = click_client.execute(sql)
    log.debug(list(rows))


def click_create_table_obs_openvpn() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS obs_openvpn
    (
        anomaly Bool,
        bootstrap_time Float32,
        confirmed Bool,
        failure String,
        input String,
        last_handshake_transaction_id Uint8,
        measurement_start_time DateTime,
        measurement_uid String,
        minivpn_version String,
        obfs4_version String,
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
        success_handshake Bool,
        success_icmp Bool,
        success_urlgrab Bool,
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
    # FIXME _click_create_table_fastpath()


def _write_rows_to_fastpath(rows: List[Dict]):
    global click_client
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
    blocking_type,
    domain,
    software_name,
    software_version,
    test_version,
    test_runtime,
    architecture,
    engine_name,
    engine_version,
    test_helper_address,
    test_helper_type
    ) VALUES
        """
    )
    settings = {"priority": 5}
    try:
        click_client.execute(sql_insert, rows, settings=settings)
    except Exception:
        log.error("Failed Clickhouse insert", exc_info=True)


def flush_fastpath_buffer():
    global fastpath_row_buffer
    log.info("Flushing fastpath buffer")
    _write_rows_to_fastpath(fastpath_row_buffer)
    fastpath_row_buffer = []


@metrics.timer("clickhouse_upsert_summary")
def clickhouse_upsert_summary(
    msm,
    scores,
    anomaly: bool,
    confirmed: bool,
    msm_failure: bool,
    blocking_type: str,
    measurement_uid: str,
    software_name: str,
    software_version: str,
    platform: str,
    test_version: str,
    test_runtime: float,
    architecture: str,
    engine_name: str,
    engine_version: str,
    test_helper_address: str,
    test_helper_type: str,
    buffer_writes=False,
) -> None:
    """Insert a row in the fastpath table. Overwrite an existing one."""
    global fastpath_row_buffer

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
    row = dict(
        measurement_uid=measurement_uid,
        report_id=nn(msm, "report_id"),
        input=input_,
        probe_cc=nn(msm, "probe_cc"),
        probe_asn=asn,
        test_name=test_name,
        test_start_time=test_start_time,
        measurement_start_time=measurement_start_time,
        scores=ujson.dumps(scores),
        platform=platform,
        anomaly=tf(anomaly),
        confirmed=tf(confirmed),
        msm_failure=tf(msm_failure),
        blocking_type=blocking_type,
        domain=domain,
        software_name=nn(msm, "software_name"),
        software_version=nn(msm, "software_version"),
        test_version=test_version,
        test_runtime=test_runtime,
        architecture=architecture,
        engine_name=engine_name,
        engine_version=engine_version,
        test_helper_address=test_helper_address,
        test_helper_type=test_helper_type,
    )

    if buffer_writes:
        # Enabled only when multithreading is not in use
        fastpath_row_buffer.append(row)
        if len(fastpath_row_buffer) < 500:
            return
        log.info("Writing to fastpath")
        rows = fastpath_row_buffer
    else:
        rows = [row]

    _write_rows_to_fastpath(rows)

    if buffer_writes:
        fastpath_row_buffer = []

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
    msm: dict, scores: dict, measurement_uid: str
) -> None:
    global click_client
    sql_insert = dedent(
        """\
    INSERT INTO obs_openvpn (
    anomaly,
    bootstrap_time,
    confirmed,
    failure,
    input,
    last_handshake_transaction_id,
    measurement_start_time,
    measurement_uid,
    minivpn_version,
    obfs4_version,
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
    success_handshake,
    success_icmp,
    success_urlgrab,
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

    anomaly = nn(msm, "success") is True
    success = bool(nn(tk, "success"))
    failure = nn(tk, "failure")
    resolver_asn_str = nn(msm, "resolver_asn")
    try:
        if resolver_asn_str.startswith("AS"):
            resolver_asn = int(resolver_asn_str[2:])
        else:
            resolver_asn = int(resolver_asn_str)
    except Exception:
        resolver_asn = 0

    nes = tk.get("network_events")
    try:
        last_transaction_id = max(e["transaction_id"] for e in nes)
    except Exception:
        last_transaction_id = 0

    row = dict(
        anomaly=anomaly,
        bootstrap_time=dget_or(tk, "bootstrap_time", 0),
        confirmed=False,
        failure=failure,
        input=nn(msm, "input"),
        last_handshake_transaction_id=last_transaction_id,
        measurement_start_time=measurement_start_time,
        measurement_uid=measurement_uid,
        minivpn_version=nn(tk, "minivpn_version"),
        obfs4_version=nn(tk, "obfs4_version"),
        obfuscation=nn(tk, "obfuscation"),
        platform=nn(msm, "platform"),
        probe_asn=asn,
        probe_cc=nn(msm, "probe_cc"),
        probe_network_name=nn(msm, "probe_network_name"),
        provider=nn(tk, "provider"),
        remote=nn(tk, "remote"),
        report_id=nn(msm, "report_id"),
        resolver_asn=resolver_asn,
        resolver_ip=nn(msm, "resolver_ip"),
        resolver_network_name=nn(msm, "resolver_network_name"),
        software_name=nn(msm, "software_name"),
        software_version=nn(msm, "software_version"),
        success=success,
        success_handshake=bool(tk.get("success_handshake")),
        success_icmp=bool(tk.get("success_icmp")),
        success_urlgrab=bool(tk.get("success_urlgrab")),
        test_runtime=dget_or(msm, "test_runtime", 0),
        test_start_time=test_start_time,
        transport=nn(tk, "transport"),
    )

    settings = {"priority": 5}
    try:
        click_client.execute(sql_insert, [row], settings=settings)
    except Exception:
        log.error("Failed Clickhouse insert", exc_info=True)


def query(query: str, query_params: dict, query_prio=5):
    global click_client
    settings = {"priority": query_prio, "max_execution_time": 28}
    q = click_client.execute(
        query, query_params, with_column_types=True, settings=settings
    )
    rows, coldata = q
    colnames, coltypes = tuple(zip(*coldata))
    return [dict(zip(colnames, row)) for row in rows]


@metrics.timer("fetch_fingerprints")
def fetch_fingerprints() -> Tuple[List, List]:
    sql = """
    SELECT name, scope, other_names, location_found, pattern_type,
        pattern, confidence_no_fp, expected_countries
    FROM fingerprints_dns
    """
    dns_fp = query(sql, {})
    sql = """
    SELECT name, scope, other_names, location_found, pattern_type,
        pattern, confidence_no_fp, expected_countries
    FROM fingerprints_http
    """
    http_fp = query(sql, {})
    return dns_fp, http_fp
