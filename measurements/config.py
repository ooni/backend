from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

CACHE_DEFAULT_TIMEOUT = None
CACHE_CONFIG = {'CACHE_TYPE': 'simple'}

CELERY_BACKEND = os.environ.get("CELERY_BACKEND", "redis://redis:6379/0")
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL",
                                   "amqp://guest@rabbitmq:5672//")

APP_ENV = os.environ.get("APP_ENV", "development")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///ooni_measurements.db")
WEBSERVER_ADDRESS = os.environ.get("WEBSERVER_ADDRESS", "0.0.0.0")
WEBSERVER_PORT = int(os.environ.get("WEBSERVER_PORT", "3000"))

BASE_URL = os.environ.get("BASE_URL",
                          "https://measurements.ooni.torproject.org/")

# This can either be a local directory (ex. /data/ooni/public/sanitised)
# or an s3 endpoint (ex. s3://ooni-public/sanitised)
REPORTS_DIR = os.environ.get("REPORTS_DIR", "s3://ooni-public/sanitised/")

WORKERS = 4

# S3 related configuration
S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID", None)
S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY", None)
S3_SESSION_TOKEN = os.environ.get("S3_SESSION_TOKEN", None)
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", None)
