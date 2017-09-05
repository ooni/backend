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

BASE_URL = os.environ.get("BASE_URL",
                          "https://measurements.ooni.torproject.org/")

AUTOCLAVED_BASE_URL = os.environ.get("AUTOCLAVED_BASE_URL",
                                      "http://datacollector.infra.ooni.io/ooni-public/autoclaved/")

# S3 related configuration
S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID", None)
S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY", None)
S3_SESSION_TOKEN = os.environ.get("S3_SESSION_TOKEN", None)
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)

# As of 2017-07-18 635830 is the latest index in the database
REPORT_INDEX_OFFSET = int(os.environ.get("REPORT_INDEX_OFFSET", "635830"))
