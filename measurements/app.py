from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import logging
import os

from flask import Flask
from flask_misaka import Misaka
from flask_cache import Cache

from measurements.database import init_db, create_tables

APP_DIR = os.path.dirname(__file__)

cache = Cache()

def init_app(app):
    # We load configurations first from the config file (where some options
    # are overridable via environment variables) or from the config file
    # pointed to by the MEASUREMENTS_CONFIG environment variable.
    # The later overrides the former.
    app.config.from_object('measurements.config')
    app.config.from_envvar('MEASUREMENTS_CONFIG', silent=True)

    if not app.debug:
        app.logger.addHandler(logging.StreamHandler())
        app.logger.setLevel(logging.INFO)
    md = Misaka(fenced_code=True)
    md.init_app(app)

    cache.init_app(app, config=app.config['CACHE_CONFIG'])

def create_app(*args, **kw):
    from measurements import views
    app = Flask(__name__)

    init_app(app)
    init_db(app)
    create_tables(app)
    views.register(app)

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        app.db_session.remove()

    return app
