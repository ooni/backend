from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

def create_tables(app):
    from . import models
    Base.metadata.create_all(bind=app.db_engine)

def init_db(app):
    app.db_engine = create_engine(
        app.config['SQLALCHEMY_DATABASE_URI'], convert_unicode=True
    )
    app.db_session = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=app.db_engine)
    )
    Base.query = app.db_session.query_property()
