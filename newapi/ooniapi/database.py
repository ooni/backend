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

from ooniapi.config import metrics

# query_time = Summary("query", "query", ["hash", ], registry=metrics.registry)
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
    """Initializes database connection"""
    application_name = _gen_application_name()
    # Unfortunately this application_name is not logged during `connection authorized`,
    # but it is used for `disconnection` event even if the client dies during query!
    query_timeout = app.config["DATABASE_STATEMENT_TIMEOUT"] * 1000
    assert query_timeout > 1000
    connargs = {
        "application_name": application_name,
        "options": f"-c statement_timeout={query_timeout}",
    }
    uri = app.config["DATABASE_URI_RO"]
    app.logger.info(f"Database URI: {uri}")
    app.db_engine = create_engine(uri, convert_unicode=True, connect_args=connargs)
    app.db_session = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=app.db_engine)
    )
    Base.query = app.db_session.query_property()

    # Set query duration limits (in milliseconds)
    app.db_session.execute(
        # "SET seq_page_cost=2;"
        # "SET enable_seqscan=off;"
        "SET idle_in_transaction_session_timeout = 6000000"
    )

    # Set up hooks to log queries and generate metrics on a hash of the query statement
    # Prevent setting hooks multiple times during functional testing
    global hooks_are_set
    if hooks_are_set:
        return

    # TODO auto reconnect

    @event.listens_for(Engine, "before_cursor_execute")
    def before_cursor_execute(
        conn, cursor, statement, params, context, execmany
    ):
        qh = query_hash(statement)
        with metrics.timer(f"query-{qh}"):
            query = cursor.mogrify(statement, params).decode()
            conn.info.setdefault("query_start_time", []).append(time.time())
            query = query.replace("\n", " ")
            app.logger.debug("Starting query %s ---- %s ----", qh, query)

    @event.listens_for(Engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, params, context, execmany):
        total_time = time.time() - conn.info["query_start_time"].pop(-1)
        qh = query_hash(statement)
        # query_time.labels(qh).observe(total_time)
        app.logger.debug("Query %s completed in %fs", qh, total_time)

    hooks_are_set = True
