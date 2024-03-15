from csv import DictWriter
from io import StringIO
import logging
from typing import Any, Dict, List, Optional, Union
from fastapi.responses import JSONResponse

import jwt


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


def commasplit(p: str) -> List[str]:
    assert p is not None
    out = set(p.split(","))
    out.discard("")
    return sorted(out)


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


def decode_jwt(token: str, key: str, **kw) -> Dict[str, Any]:
    tok = jwt.decode(token, key, algorithms=["HS256"], **kw)
    return tok


def create_jwt(payload: dict, key: str) -> str:
    token = jwt.encode(payload, key, algorithm="HS256")
    if isinstance(token, bytes):
        return token.decode()
    else:
        return token


def get_client_token(authorization: str, jwt_encryption_key: str):
    try:
        assert authorization.startswith("Bearer ")
        token = authorization[7:]
        return decode_jwt(token, audience="user_auth", key=jwt_encryption_key)
    except:
        return None


def get_client_role(authorization: str, jwt_encryption_key: str) -> str:
    """Raise exception for unlogged users"""
    tok = get_client_token(authorization, jwt_encryption_key)
    assert tok
    return tok["role"]


def get_account_id_or_none(
    authorization: str, jwt_encryption_key: str
) -> Optional[str]:
    """Returns None for unlogged users"""
    tok = get_client_token(authorization, jwt_encryption_key)
    if tok:
        return tok["account_id"]
    return None


def get_account_id_or_raise(authorization: str, jwt_encryption_key: str) -> str:
    """Raise exception for unlogged users"""
    tok = get_client_token(authorization, jwt_encryption_key)
    if tok:
        return tok["account_id"]
    raise Exception


def get_account_id(authorization: str, jwt_encryption_key: str):
    # TODO: switch to get_account_id_or_none
    tok = get_client_token(authorization, jwt_encryption_key)
    if not tok:
        return jerror("Authentication required", 401)

    return tok["account_id"]
