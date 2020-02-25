from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from hashlib import shake_128
import os
import time

from sqlalchemy import event
from sqlalchemy.engine import Engine

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy_utils import database_exists, create_database

from measurements.config import metrics

from prometheus_client import Summary

query_time = Summary("query", "query", ["hash", ], registry=metrics.registry)
Base = declarative_base()


def _gen_application_name():
    try:
        machine_id = "/etc/machine-id"
        with open(machine_id) as fd:
            mid = fd.read(8)

    except FileNotFoundError:
        mid = "macos"

    pid = os.getpid()
    return f"api-{mid}-{pid}"


def query_hash(q: str) -> str:
    """Short hash used to identify query statements.
    Allows correlating query statements between API logs and metrics
    """
    return shake_128(q.encode()).hexdigest(4)


hooks_are_set = False

def init_db(app):
    application_name = _gen_application_name()
    # Unfortunately this application_name is not logged during `connection authorized`,
    # but it is used for `disconnection` event even if the client dies during query!
    connect_args = {
        "application_name": application_name,
        "options": "-c statement_timeout={:d}".format(
            app.config["DATABASE_STATEMENT_TIMEOUT"]
        ),
    }
    app.db_engine = create_engine(
        app.config["DATABASE_URL"], convert_unicode=True, connect_args=connect_args
    )
    if not database_exists(app.db_engine.url):
        create_database(app.db_engine.url)
    app.db_session = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=app.db_engine)
    )
    Base.query = app.db_session.query_property()

    # Set query duration limits (in milliseconds)
    app.db_session.execute(
        "SET statement_timeout = 30000;"
        "SET idle_in_transaction_session_timeout = 60000"
    )

    # Set up hooks to log queries and generate metrics on a hash of the query statement
    # Prevent setting hooks multiple times during functional testing
    global hooks_are_set
    if hooks_are_set:
        return

    @event.listens_for(Engine, "before_cursor_execute")
    def before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        qh = query_hash(statement)
        query = cursor.mogrify(statement, parameters).decode()
        conn.info.setdefault("query_start_time", []).append(time.time())
        app.logger.debug("Starting query %s ---- %s ----", qh, query)

    @event.listens_for(Engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        total_time = time.time() - conn.info["query_start_time"].pop(-1)
        qh = query_hash(statement)
        query_time.labels(qh).observe(total_time)
        app.logger.debug("Query %s completed in %fs", qh, total_time)

    hooks_are_set = True
