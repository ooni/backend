from csv import DictWriter
from io import StringIO
from sys import byteorder
from os import urandom
import logging
from base64 import b64encode
from datetime import datetime, timezone
from typing import List
from fastapi import Response
from fastapi.responses import JSONResponse
from .config import Settings


log = logging.getLogger(__name__)


INTERVAL_UNITS = dict(s=1, m=60, h=3600, d=86400)


def cachedjson(interval: str, *a, **kw) -> JSONResponse:
    """Jsonify and add cache expiration"""
    max_age = int(interval[:-1]) * INTERVAL_UNITS[interval[-1]]
    headers = {"Cache-Control": f"max-age={max_age}"}
    return JSONResponse(content=dict(*a, **kw), headers=headers)


def nocachejson(*a, **kw) -> JSONResponse:
    """Jsonify and explicitely prevent caching"""
    headers = {"Cache-Control": "no-cache, max-age=0"}
    return JSONResponse(content=dict(*a, **kw), headers=headers)


def jerror(msg, code=400, **kw) -> JSONResponse:
    headers = {"Cache-Control": "no-cache"}
    return JSONResponse(content=dict(msg=msg, **kw), status_code=code, headers=headers)


def setcacheresponse(interval: str, response: Response):
    max_age = int(interval[:-1]) * INTERVAL_UNITS[interval[-1]]
    response.headers["Cache-Control"] = f"max-age={max_age}"


def setnocacheresponse(response: Response):
    response.headers["Cache-Control"] = "no-cache"


def commasplit(p: str) -> List[str]:
    assert p is not None
    out = set(p.split(","))
    out.discard("")
    return sorted(out)


def convert_to_csv(r) -> str:
    """Convert aggregation result dict/list to CSV"""
    csvf = StringIO()
    if len(r) == 0:
        return ""
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


def generate_random_intuid(collector_id: str) -> int:
    try:
        collector_id = int(collector_id)
    except ValueError:
        collector_id = 0
    randint = int.from_bytes(urandom(4), byteorder)
    return randint * 100 + collector_id


def generate_report_id(test_name, settings: Settings, cc: str, asn_i: int) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cid = settings.collector_id
    rand = b64encode(urandom(12), b"oo").decode()
    stn = test_name.replace("_", "")
    rid = f"{ts}_{stn}_{cc}_{asn_i}_n{cid}_{rand}"
    return rid
