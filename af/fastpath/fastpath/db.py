"""
OONI Fastpath

Database connector

See ../../oometa/017-fastpath.install.sql for the tables structure

"""

from textwrap import dedent
from urllib.parse import urlparse
import logging

import psycopg2  # debdeps: python3-psycopg2
from psycopg2.extras import Json

import ujson

from fastpath.metrics import setup_metrics

log = logging.getLogger("fastpath.db")
metrics = setup_metrics(name="fastpath.db")

conn = None
_autocommit_conn = None


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
    input_ = msm.get("input", None)

    if test_name == "meek_fronted_requests_test" and isinstance(input_, list):
        domain = None if input_ is None else urlparse(input_[0]).netloc
        input_ = ":".join(input_)
    else:
        domain = None if input_ is None else urlparse(input_).netloc

    args = (
        measurement_uid,
        msm["report_id"],
        domain,
        input_,
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
