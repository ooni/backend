from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

CACHE_DEFAULT_TIMEOUT = None
CACHE_CONFIG = {'CACHE_TYPE': 'simple'}

SQLALCHEMY_DATABASE_URI = 'sqlite:///ooni_measurements.db'
WEBSERVER_ADDRESS = "0.0.0.0"
WEBSERVER_PORT = 3001

BASE_URL = 'https://measurements.ooni.torproject.org/'
REPORTS_DIRECTORY = '/data/ooni/public/sanitised/'

WORKERS = 4
