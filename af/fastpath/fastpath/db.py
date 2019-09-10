"""
OONI Fastpath

Database connector

See ../../oometa/017-fastpath.install.sql for the tables structure

"""

import logging

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


def _ping():
    q = "SELECT pg_postmaster_start_time();"
    with conn.cursor() as cur:
        cur.execute(q)
        row = cur.fetchone()
        log.info("Database start time: %s", row[0])
        # log.info("Query: %s", cur.query)


def setup():
    global conn, _autocommit_conn
    dsn = f"host={DB_HOST} user={DB_USER} dbname={DB_NAME} password={DB_PASSWORD}"
    log.info("Connecting to database: %r", dsn)
    conn = psycopg2.connect(dsn)
    _autocommit_conn = psycopg2.connect(dsn)
    _autocommit_conn.autocommit = True
    # _ping()


@metrics.timer("upsert_summary")
def upsert_summary(msm, summary, filename):
    """Insert a row in the fastpath_scores table. Overwrite an existing one.
    """
    tpl = """
    INSERT INTO fastpath (report_id, input, probe_cc, probe_asn, test_name, test_start_time, measurement_start_time, filename)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT ON CONSTRAINT fastpath_pkey DO UPDATE SET
        probe_cc = excluded.probe_cc,
        probe_asn = excluded.probe_asn,
        test_name = excluded.test_name,
        test_start_time = excluded.test_start_time,
        measurement_start_time = excluded.measurement_start_time,
        filename = excluded.filename
    """
    asn = int(msm["probe_asn"][2:])  # AS123
    args = (
        msm["report_id"],
        msm["input"],
        msm["probe_cc"],
        asn,
        msm["test_name"],
        msm["test_start_time"],
        msm["measurement_start_time"],
        filename
    )

    tpl_scores = """
    INSERT INTO fastpath_scores (report_id, input, probe_cc, probe_asn, test_name, test_start_time, measurement_start_time, scores)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT ON CONSTRAINT fastpath_scores_pkey DO UPDATE SET
        probe_cc = excluded.probe_cc,
        probe_asn = excluded.probe_asn,
        test_name = excluded.test_name,
        test_start_time = excluded.test_start_time,
        measurement_start_time = excluded.measurement_start_time,
        scores = excluded.scores
    """
    args_scores = (
        msm["report_id"],
        msm["input"],
        msm["probe_cc"],
        asn,
        msm["test_name"],
        msm["test_start_time"],
        msm["measurement_start_time"],
        Json(summary["scores"], dumps=ujson.dumps),
    )

    with _autocommit_conn.cursor() as cur:
        cur.execute(tpl, args)
        cur.execute(tpl_scores, args_scores)
