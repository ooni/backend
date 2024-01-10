from csv import DictWriter
from io import StringIO
import logging
from typing import Dict, List, Optional, Union
from fastapi.responses import JSONResponse

import clickhouse_driver
import clickhouse_driver.errors

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.selectable import Select


from .config import settings

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
