from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

CACHE_DEFAULT_TIMEOUT = None
CACHE_CONFIG = {'CACHE_TYPE': 'simple'}

APP_ENV = os.environ.get("APP_ENV", "development")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///ooni_measurements.db")
WEBSERVER_ADDRESS = os.environ.get("WEBSERVER_ADDRESS", "0.0.0.0")
WEBSERVER_PORT = int(os.environ.get("WEBSERVER_PORT", "3000"))

BASE_URL = 'https://measurements.ooni.torproject.org/'
REPORTS_DIRECTORY = '/data/ooni/public/sanitised/'

WORKERS = 4
