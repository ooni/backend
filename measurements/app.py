from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import logging
import os

from celery import Celery

from flask import Flask
from flask_misaka import Misaka
from flask_cors import CORS
from flask_cache import Cache

from measurements import config
from measurements.database import init_db, create_tables
from measurements.filestore import init_filestore

APP_DIR = os.path.dirname(__file__)

cache = Cache()
celery = Celery(__name__,
                backend=config.CELERY_BACKEND,
                broker=config.CELERY_BROKER_URL)


def init_app(app):
    # We load configurations first from the config file (where some options
    # are overridable via environment variables) or from the config file
    # pointed to by the MEASUREMENTS_CONFIG environment variable.
    # The later overrides the former.
    app.config.from_object('measurements.config')
    app.config.from_envvar('MEASUREMENTS_CONFIG', silent=True)

    app.logger.addHandler(logging.StreamHandler())

    if app.config['APP_ENV'] == 'production':
        app.logger.setLevel(logging.WARNING)
    elif app.config['APP_ENV'] == 'development':
        app.logger.setLevel(logging.DEBUG)

    # Set the jinja templates to reload when in development
    if app.config['APP_ENV'] == 'development':
        app.jinja_env.auto_reload = True
        app.config['TEMPLATES_AUTO_RELOAD'] = True

    for key in app.config.keys():
        # Do not log, even in debug, anything containing the work "SECRET"
        if "SECRET" in key:
            continue
        app.logger.debug("{}: {}".format(key, app.config[key]))

    md = Misaka(fenced_code=True)
    md.init_app(app)

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    cache.init_app(app, config=app.config['CACHE_CONFIG'])

def create_app(*args, **kw):
    from measurements import views
    from measurements.tasks import setup_period_tasks
    from measurements.utils import init_celery

    app = Flask(__name__)

    # Order matters
    init_app(app)
    init_db(app)
    init_filestore(app)
    init_celery(app, celery)
    setup_period_tasks(app)

    create_tables(app)
    views.register(app)

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        app.db_session.remove()

    return app
