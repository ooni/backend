"""
OONI Fastpath

Database connector

See ../../oometa/017-fastpath.install.sql for the tables structure

"""

from datetime import datetime
from enum import IntEnum
from textwrap import dedent
from urllib.parse import urlparse
from typing import List, Tuple, Dict, Optional, Any
import logging
import time

# Errors from the connection or the server: worth retrying an insert, except
# for server errors about the rows' data (BAD_DATA_ERROR_CODES below).
# NetworkError and ServerException are defined in clickhouse-driver:
# https://github.com/mymarilyn/clickhouse-driver/blob/0.2.11/clickhouse_driver/errors.py
RETRIABLE_INSERT_ERRORS: Tuple = (EOFError, OSError)
try:
    # debdeps: python3-clickhouse-driver
    from clickhouse_driver import Client as Clickhouse
    from clickhouse_driver.errors import NetworkError, ServerException

    RETRIABLE_INSERT_ERRORS += (NetworkError, ServerException)
except ImportError:
    pass
import ujson

from fastpath.metrics import setup_metrics


class ClickHouseError(IntEnum):
    """ClickHouse server error codes, as ServerException.code reports them"""

    CANNOT_PARSE_TEXT = 6
    CANNOT_PARSE_INPUT_ASSERTION_FAILED = 27
    CANNOT_PARSE_DATE = 38
    CANNOT_PARSE_DATETIME = 41
    TYPE_MISMATCH = 53
    CANNOT_CONVERT_TYPE = 70
    CANNOT_PARSE_NUMBER = 72
    INCORRECT_DATA = 117
    CANNOT_READ_ARRAY_FROM_TEXT = 130
    TOO_LARGE_STRING_SIZE = 131
    VALUE_IS_OUT_OF_RANGE_OF_DATA_TYPE = 321
    CANNOT_INSERT_NULL_IN_ORDINARY_COLUMN = 349
    CANNOT_PARSE_UUID = 376
    CANNOT_PARSE_BOOL = 467
    UNICODE_ERROR = 760


# Server errors about the data in the rows: retrying fails the same way, so
# insert_rows splits the batch to drop only the bad rows instead. The codes are
# from ClickHouse's src/Common/ErrorCodes.cpp, with the same numbers in every
# version we upgrade through (24.8.6.70 to 26.8.9.10):
# https://github.com/ClickHouse/ClickHouse/blob/v24.8.6.70-lts/src/Common/ErrorCodes.cpp
# https://github.com/ClickHouse/ClickHouse/blob/v26.8.9.10-lts/src/Common/ErrorCodes.cpp
# UNICODE_ERROR appears in 26.3:
# https://github.com/ClickHouse/ClickHouse/blob/v26.3.17.110-lts/src/Common/ErrorCodes.cpp
# Every other server error is retried: one that every insert hits (e.g. a bad
# password) then fills the queue, and probes send to another fastpath.
BAD_DATA_ERROR_CODES = frozenset(
    {
        ClickHouseError.CANNOT_PARSE_TEXT,
        ClickHouseError.CANNOT_PARSE_INPUT_ASSERTION_FAILED,
        ClickHouseError.CANNOT_PARSE_DATE,
        ClickHouseError.CANNOT_PARSE_DATETIME,
        ClickHouseError.TYPE_MISMATCH,
        ClickHouseError.CANNOT_CONVERT_TYPE,
        ClickHouseError.CANNOT_PARSE_NUMBER,
        ClickHouseError.INCORRECT_DATA,
        ClickHouseError.CANNOT_READ_ARRAY_FROM_TEXT,
        ClickHouseError.TOO_LARGE_STRING_SIZE,
        ClickHouseError.VALUE_IS_OUT_OF_RANGE_OF_DATA_TYPE,
        ClickHouseError.CANNOT_INSERT_NULL_IN_ORDINARY_COLUMN,
        ClickHouseError.CANNOT_PARSE_UUID,
        ClickHouseError.CANNOT_PARSE_BOOL,
        ClickHouseError.UNICODE_ERROR,
    }
)


def _is_retriable_insert_error(exc: BaseException) -> bool:
    if not isinstance(exc, RETRIABLE_INSERT_ERRORS):
        return False
    # clickhouse-driver's own errors carry a class-level code too, but none of
    # the retriable ones is a data error code
    return getattr(exc, "code", None) not in BAD_DATA_ERROR_CODES
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


# Inserts that fail because of the connection or the server are retried
# with an exponential backoff: 1, 2 and 4 seconds
INSERT_ATTEMPTS = 4
INSERT_BACKOFF_SECONDS = 1.0


def insert_rows(sql: str, rows: List[Dict], settings: Dict) -> int:
    """Insert rows. Retry errors from the connection or the server with a
    backoff. Other errors come from the rows themselves (the driver could not
    serialize a value, or the server rejected one: BAD_DATA_ERROR_CODES): split
    the batch to insert every other row and drop the bad ones. Returns the
    number of rows that were not inserted.
    """
    if not rows:
        return 0
    for attempt in range(1, INSERT_ATTEMPTS + 1):
        try:
            click_client.execute(sql, rows, settings=settings)
            return 0
        except Exception as e:
            if not _is_retriable_insert_error(e):
                if len(rows) == 1:
                    uid = rows[0].get("measurement_uid")
                    log.error(f"Clickhouse insert rejected {uid}", exc_info=True)
                    metrics.incr("clickhouse_insert_bad_rows")
                    return 1
                break
            if attempt == INSERT_ATTEMPTS:
                log.error(f"Failed Clickhouse insert of {len(rows)} rows", exc_info=True)
                metrics.incr("clickhouse_insert_dropped_rows", len(rows))
                return len(rows)
            delay = INSERT_BACKOFF_SECONDS * 2 ** (attempt - 1)
            log.warning(f"Clickhouse insert failed, retrying in {delay}s", exc_info=True)
            metrics.incr("clickhouse_insert_retry")
            time.sleep(delay)

    mid = len(rows) // 2
    return insert_rows(sql, rows[:mid], settings) + insert_rows(sql, rows[mid:], settings)


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
    test_helper_type,
    ooni_run_link_id,
    is_verified
    ) VALUES
        """
    )
    settings = {"priority": 5}
    insert_rows(sql_insert, rows, settings)


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
    ooni_run_link_id: Optional[int],
    is_verified: str,
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
        ooni_run_link_id=ooni_run_link_id,
        is_verified=is_verified,
    )

    if buffer_writes:
        # Enabled only when multithreading is not in use
        fastpath_row_buffer.append(row)
        if len(fastpath_row_buffer) < 10000:
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
    insert_rows(sql_insert, [row], settings)


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
