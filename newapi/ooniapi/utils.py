from datetime import datetime
from flask.json import jsonify

ISO_TIMESTAMP_SHORT = "%Y%m%dT%H%M%SZ"
OONI_EPOCH = datetime(2012, 12, 5)

INTERVAL_UNITS = dict(s=1, m=60, h=3600, d=86400)


def cachedjson(interval: str, *a, **kw):
    """Jsonify and add cache expiration"""
    resp = jsonify(*a, **kw)
    unit = interval[-1]
    value = int(interval[:-1])
    resp.cache_control.max_age = value * INTERVAL_UNITS[unit]
    return resp


def nocachejson(*a, **kw):
    """Jsonify and explicitely prevent caching"""
    resp = jsonify(*a, **kw)
    resp.cache_control.max_age = 0
    resp.cache_control.no_cache = True
    return resp
