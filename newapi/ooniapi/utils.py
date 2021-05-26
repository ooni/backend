from datetime import datetime
from flask.json import jsonify

ISO_TIMESTAMP_SHORT = "%Y%m%dT%H%M%SZ"
OONI_EPOCH = datetime(2012, 12, 5)


def cachedjson(interval_hours: int, *a, **kw):
    """Jsonify and add cache expiration"""
    resp = jsonify(*a, **kw)
    resp.cache_control.max_age = interval_hours * 3600
    return resp


def nocachejson(*a, **kw):
    """Jsonify and explicitely prevent caching"""
    resp = jsonify(*a, **kw)
    resp.cache_control.max_age = 0
    resp.cache_control.no_cache = True
    return resp
