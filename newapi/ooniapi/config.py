from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os

from flask import request

import statsd  # debdeps: python3-statsd

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

CACHE_DEFAULT_TIMEOUT = None
CACHE_CONFIG = {"CACHE_TYPE": "simple"}

APP_ENV = os.environ.get("APP_ENV", "development")

# As of 2017-07-18 635830 is the latest index in the database
REPORT_INDEX_OFFSET = int(os.environ.get("REPORT_INDEX_OFFSET", "635830"))

REQID_HDR = "X-Request-ID"

metrics = statsd.StatsClient("localhost", 8125, prefix="ooni-api")


def request_id():
    if request:
        return request.headers.get(REQID_HDR)
    return None
