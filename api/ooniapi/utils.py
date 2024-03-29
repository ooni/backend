from csv import DictWriter
from datetime import datetime
from io import StringIO
from os import urandom
from sys import byteorder

from flask import request, make_response, Response
from flask.json import jsonify

import ujson

ISO_TIMESTAMP_SHORT = "%Y%m%dT%H%M%SZ"
OONI_EPOCH = datetime(2012, 12, 5)

INTERVAL_UNITS = dict(s=1, m=60, h=3600, d=86400)


def cachedjson(interval: str, *a, **kw) -> Response:
    """Jsonify and add cache expiration"""
    resp = jsonify(*a, **kw)
    unit = interval[-1]
    value = int(interval[:-1])
    resp.cache_control.max_age = value * INTERVAL_UNITS[unit]
    return resp


def nocachejson(*a, **kw) -> Response:
    """Jsonify and explicitely prevent caching"""
    resp = jsonify(*a, **kw)
    resp.cache_control.max_age = 0
    resp.cache_control.no_cache = True
    return resp


def jerror(msg, code=400, **kw) -> Response:
    resp = make_response(jsonify(error=msg, **kw), code)
    resp.cache_control.no_cache = True
    return resp


def convert_to_csv(r) -> str:
    """Convert aggregation result dict/list to CSV"""
    csvf = StringIO()
    if isinstance(r, dict):
        # 0-dimensional data
        fieldnames = sorted(r.keys())
        writer = DictWriter(csvf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(r)

    else:
        fieldnames = sorted(r[0].keys())
        writer = DictWriter(csvf, fieldnames=fieldnames)
        writer.writeheader()
        for row in r:
            writer.writerow(row)

    result = csvf.getvalue()
    csvf.close()
    return result


def req_json():
    # Some probes are not setting the JSON mimetype.
    # if request.is_json():
    #    return request.json
    # TODO: switch to request.get_json(force=True) ?
    return ujson.loads(request.data)


def generate_random_intuid(current_app) -> int:
    try:
        collector_id = int(current_app.config["COLLECTOR_ID"])
    except ValueError:
        collector_id = 0
    randint = int.from_bytes(urandom(4), byteorder)
    return randint * 100 + collector_id
