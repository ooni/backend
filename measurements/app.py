from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import logging
import os

from flask import Flask
from flask_misaka import Misaka

from . import views
from .database import init_db, create_tables

APP_DIR = os.path.dirname(__file__)


def init_app(app):
    app.config.from_object('measurements.config')

    config_file = os.environ.get('MEASUREMENTS_CONFIG', None)
    if config_file is not None:
        app.config.from_pyfile(config_file, silent=True)

    if not app.debug:
        app.logger.addHandler(logging.StreamHandler())
        app.logger.setLevel(logging.INFO)
    md = Misaka(fenced_code=True)
    md.init_app(app)


def create_app():
    app = Flask(__name__)

    init_app(app)
    init_db(app)
    create_tables(app)
    views.register(app)

    return app
