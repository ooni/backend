"""
OONI Fastpath

Database connector

See ../../oometa/017-fastpath.install.sql for the tables structure

"""

from textwrap import dedent
import logging
import os
import time
import random

import psycopg2  # debdeps: python3-psycopg2
from psycopg2.extras import Json

import ujson

from fastpath.metrics import setup_metrics

log = logging.getLogger("fastpath.db")
metrics = setup_metrics(name="fastpath.db")

conn = None
_autocommit_conn = None

DB_HOST = "hkgmetadb.infra.ooni.io"
DB_USER = "shovel"
DB_NAME = "metadb"
DB_PASSWORD = "yEqgNr2eXvgG255iEBxVeP"  # This is already made public
FREE_SPACE_GB = 5


def _ping():
    q = "SELECT pg_postmaster_start_time();"
    with conn.cursor() as cur:
        cur.execute(q)
        row = cur.fetchone()
        log.info("Database start time: %s", row[0])


def setup(conf) -> None:
    global conn, _autocommit_conn
    if conf.db_uri:
        dsn = conf.db_uri
    else:
        dsn = f"host={DB_HOST} user={DB_USER} dbname={DB_NAME} password={DB_PASSWORD}"
    log.info("Connecting to database: %r", dsn)
    conn = psycopg2.connect(dsn)
    _autocommit_conn = psycopg2.connect(dsn)
    _autocommit_conn.autocommit = True
    _ping()


@metrics.timer("upsert_summary")
def upsert_summary(
    msm,
    scores,
    anomaly: bool,
    confirmed: bool,
    msm_failure: bool,
    tid,
    filename,
    update,
) -> None:
    """Insert a row in the fastpath_scores table. Overwrite an existing one.
    """
    sql_base_tpl = dedent(
        """\
    INSERT INTO fastpath (tid, report_id, input, probe_cc, probe_asn, test_name,
        test_start_time, measurement_start_time, platform, filename, scores,
        anomaly, confirmed, msm_failure)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT ON CONSTRAINT fastpath_pkey DO
    """
    )
    sql_update = dedent(
        """\
    UPDATE SET
        report_id = excluded.report_id,
        input = excluded.input,
        probe_cc = excluded.probe_cc,
        probe_asn = excluded.probe_asn,
        test_name = excluded.test_name,
        test_start_time = excluded.test_start_time,
        measurement_start_time = excluded.measurement_start_time,
        platform = excluded.platform,
        filename = excluded.filename,
        scores = excluded.scores,
        anomaly = excluded.anomaly,
        confirmed = excluded.confirmed,
        msm_failure = excluded.msm_failure
    """
    )
    sql_noupdate = " NOTHING"

    tpl = sql_base_tpl + (sql_update if update else sql_noupdate)

    asn = int(msm["probe_asn"][2:])  # AS123
    platform = "unset"
    if "annotations" in msm and isinstance(msm["annotations"], dict):
        platform = msm["annotations"].get("platform", "unset")
    args = (
        tid,
        msm["report_id"],
        msm.get("input", None),
        msm["probe_cc"],
        asn,
        msm["test_name"],
        msm["test_start_time"],
        msm["measurement_start_time"],
        platform,
        filename,
        Json(scores, dumps=ujson.dumps),
        anomaly,
        confirmed,
        msm_failure,
    )

    # Send notification using pg_notify
    # TODO: do not send notifications during manual run or in devel mode
    cols = (
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
            # log.debug(cur.query.decode())
        except psycopg2.ProgrammingError:
            log.error("upsert syntax error in %r", tpl, exc_info=True)
            return

        if cur.rowcount == 0 and not update:
            metrics.incr("report_id_input_db_collision")
            inp = msm.get("input", "<no input>")
            log.info(f"report_id / input collision {msm['report_id']} {inp}")
            return

        notification = {k: msm.get(k, None) for k in cols}
        notification["trivial_id"] = tid
        notification["scores"] = scores
        notification_json = ujson.dumps(notification)
        q = f"SELECT pg_notify('fastpath', '{notification_json}');"
        cur.execute(q)

@metrics.timer("trim_old_measurements")
def trim_old_measurements(conf):
    """Trim old measurement files on disk
    """
    # TODO move this out of db.py
    t = time.time()
    if trim_old_measurements._next_run > t:
        return

    trim_old_measurements._next_run = t + 3600
    s = os.statvfs(conf.msmtdir)
    free_gb = s.f_bavail * s.f_bsize / 2 ** 30
    if free_gb > FREE_SPACE_GB:
        return

    log.debug("Starting file trimming: %d GB over threshold", FREE_SPACE_GB - free_gb)
    # Delete files older than 2 days, ignoring race conditions
    time_threshold = time.time() - 3600 * 48
    file_cnt = 0
    for f in conf.msmtdir.glob("*.lz4"):
        try:
            if f.stat().st_mtime < time_threshold:
                f.unlink()
                file_cnt += 1
        except FileNotFoundError:
            pass  # Likely deleted by another worker process

    log.debug("Deleted %d files", file_cnt)
    metrics.incr("deleted_files", file_cnt)


# Skew processes to run at different times
random.seed(os.getpid())
trim_old_measurements._next_run = time.time() + random.randrange(2, 30)
