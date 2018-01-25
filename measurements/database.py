from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import time

from sqlalchemy import event
from sqlalchemy.engine import Engine

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy_utils import database_exists, create_database

from measurements.config import request_id

Base = declarative_base()

def init_db(app):
    app.db_engine = create_engine(
        app.config['DATABASE_URL'], convert_unicode=True
    )
    if not database_exists(app.db_engine.url):
        create_database(app.db_engine.url)
    app.db_session = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=app.db_engine)
    )
    Base.query = app.db_session.query_property()
    init_query_logging(app)

    @event.listens_for(app.db_session, 'after_begin')
    def after_begin(session, transaction, connection):
        reqid = request_id()
        if not reqid:
            reqid = 'measurements'
        session.execute('set application_name = :reqid', {'reqid': reqid})

QUERY_TIME_THRESHOLD = 60.0 # Time in seconds after which we will start logging warnings for too long queries

def init_query_logging(app):
    @event.listens_for(Engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault('query_start_time', []).append(time.time())
        app.logger.debug("Start Query: %s", statement)

    @event.listens_for(Engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        total_time = time.time() - conn.info['query_start_time'].pop(-1)
        app.logger.debug("Query Complete!")
        app.logger.debug("Total Time: %f", total_time)

        if total_time >= QUERY_TIME_THRESHOLD:
            app.logger.warning("Query: %s", statement)
            app.logger.warning("Took too much time: %f", total_time)
