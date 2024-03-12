from csv import DictWriter
from io import StringIO
import logging
from typing import Any, Dict, List, Optional, Union
from fastapi import HTTPException, Header
from fastapi.responses import JSONResponse

import jwt
import clickhouse_driver
import clickhouse_driver.errors

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.selectable import Select


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


Query = Union[str, TextClause, Select]


def _run_query(
    db: clickhouse_driver.Client, query: Query, query_params: dict, query_prio=3
):
    # settings = {"priority": query_prio, "max_execution_time": 28}
    settings = {}
    if isinstance(query, (Select, TextClause)):
        query = str(query.compile(dialect=postgresql.dialect()))
    try:
        q = db.execute(query, query_params, with_column_types=True, settings=settings)
    except clickhouse_driver.errors.ServerException as e:
        log.info(e.message)
        raise Exception("Database query error")

    rows, coldata = q  # type: ignore
    colnames, coltypes = tuple(zip(*coldata))
    return colnames, rows


def query_click(
    db: clickhouse_driver.Client, query: Query, query_params: dict, query_prio=3
) -> List[Dict]:
    colnames, rows = _run_query(db, query, query_params, query_prio=query_prio)
    return [dict(zip(colnames, row)) for row in rows]  # type: ignore


def query_click_one_row(
    db: clickhouse_driver.Client, query: Query, query_params: dict, query_prio=3
) -> Optional[dict]:
    colnames, rows = _run_query(db, query, query_params, query_prio=query_prio)
    for row in rows:
        return dict(zip(colnames, row))  # type: ignore

    return None


def insert_click(db: clickhouse_driver.Client, query: Query, rows: list) -> int:
    assert isinstance(rows, list)
    settings = {"priority": 1, "max_execution_time": 300}  # query_prio
    return db.execute(query, rows, types_check=True, settings=settings)  # type: ignore


def optimize_table(db: clickhouse_driver.Client, tblname: str) -> None:
    settings = {"priority": 1, "max_execution_time": 300}  # query_prio
    sql = f"OPTIMIZE TABLE {tblname} FINAL"
    db.execute(sql, {}, settings=settings)


def raw_query(
    db: clickhouse_driver.Client, query: Query, query_params: dict, query_prio=1
):
    settings = {"priority": query_prio, "max_execution_time": 300}
    q = db.execute(query, query_params, with_column_types=True, settings=settings)
    return q


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
