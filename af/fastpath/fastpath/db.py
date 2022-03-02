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

import psycopg2  # debdeps: python3-psycopg2
from psycopg2.extras import Json

try:
    # debdeps: python3-clickhouse-driver
    from clickhouse_driver import Client as Clickhouse
except ImportError:
    pass
import ujson

from fastpath.metrics import setup_metrics

log = logging.getLogger("fastpath.db")
metrics = setup_metrics(name="fastpath.db")

conn = None
_autocommit_conn = None

click_client: Clickhouse

# # PostgreSQL backend


def _ping():
    q = "SELECT pg_postmaster_start_time();"
    with conn.cursor() as cur:
        cur.execute(q)
        row = cur.fetchone()
        log.info("Database start time: %s", row[0])


def setup(conf) -> None:
    global conn, _autocommit_conn
    log.info("Connecting to database")
    conn = psycopg2.connect(conf.db_uri)
    _autocommit_conn = psycopg2.connect(conf.db_uri)
    _autocommit_conn.autocommit = True
    _ping()


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


@metrics.timer("upsert_summary")
def upsert_summary(
    msm,
    scores,
    anomaly: bool,
    confirmed: bool,
    msm_failure: bool,
    measurement_uid: str,
    software_name: str,
    software_version: str,
    platform: str,
    update: bool,
) -> None:
    """Insert a row in the fastpath_scores table. Overwrite an existing one."""
    sql_base_tpl = dedent(
        """\
    INSERT INTO fastpath (measurement_uid, report_id, domain, input, probe_cc, probe_asn, test_name,
        test_start_time, measurement_start_time, platform, software_name, software_version, scores,
        anomaly, confirmed, msm_failure)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT ON CONSTRAINT fastpath_pkey DO
    """
    )
    sql_update = dedent(
        """\
    UPDATE SET
        report_id = excluded.report_id,
        domain = excluded.domain,
        input = excluded.input,
        probe_cc = excluded.probe_cc,
        probe_asn = excluded.probe_asn,
        test_name = excluded.test_name,
        test_start_time = excluded.test_start_time,
        measurement_start_time = excluded.measurement_start_time,
        platform = excluded.platform,
        software_name = excluded.software_name,
        software_version = excluded.software_version,
        scores = excluded.scores,
        anomaly = excluded.anomaly,
        confirmed = excluded.confirmed,
        msm_failure = excluded.msm_failure
    """
    )
    sql_noupdate = " NOTHING"

    tpl = sql_base_tpl + (sql_update if update else sql_noupdate)

    # TODO: remove msmt parsing from upsert_summary
    asn = int(msm["probe_asn"][2:])  # AS123
    test_name = msm.get("test_name", None)
    input_, domain = extract_input_domain(msm, test_name)

    args = (
        measurement_uid,
        msm["report_id"],
        domain or None,
        input_ or None,
        msm["probe_cc"],
        asn,
        test_name,
        msm["test_start_time"],
        msm["measurement_start_time"],
        platform,
        software_name,
        software_version,
        Json(scores, dumps=ujson.dumps),
        anomaly,
        confirmed,
        msm_failure,
    )

    # Send notification using pg_notify
    # TODO: do not send notifications during manual run or in devel mode
    notif_cols = (
        "report_id",
        "input",
        "probe_cc",
        "probe_asn",
        "test_name",
        "test_start_time",
        "measurement_start_time",
    )

    assert _autocommit_conn
    with _autocommit_conn.cursor() as cur:
        try:
            cur.execute(tpl, args)
        except psycopg2.ProgrammingError:
            log.error("upsert syntax error in %r", tpl, exc_info=True)
            return

        if cur.rowcount == 0:
            if update:
                log.error("Failed to upsert")
            else:
                metrics.incr("measurement_noupsert_count")
                log.info(f"measurement tid/uid collision")
                return
        else:
            metrics.incr("measurement_upsert_count")

        # TODO: event detector not deployed on AMS-PG
        # notification = {k: msm.get(k, None) for k in notif_cols}
        # notification["measurement_uid"] = msmt_uid
        # notification["scores"] = scores
        # notification_json = ujson.dumps(notification)
        # q = f"SELECT pg_notify('fastpath', '{notification_json}');"
        # cur.execute(q)


# # Clickhouse


def query_click(query, query_params):
    q = click_client.execute(query, query_params, with_column_types=True)
    rows, coldata = q
    colnames, coltypes = tuple(zip(*coldata))

    for row in rows:
        yield dict(zip(colnames, row))


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
        nn(msm, "software_name"),
        nn(msm, "software_version"),
    ]

    try:
        click_client.execute(sql_insert, [row])
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
