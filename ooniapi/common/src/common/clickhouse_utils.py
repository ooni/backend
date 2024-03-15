import logging
from typing import Dict, List, Optional, Union
import clickhouse_driver
import clickhouse_driver.errors

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.selectable import Select

log = logging.getLogger(__name__)

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
