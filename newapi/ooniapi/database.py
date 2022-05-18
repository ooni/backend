from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from hashlib import shake_128
from typing import Optional, List, Dict, Union
import os

from flask import current_app

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.selectable import Select

# debdeps: python3-clickhouse-driver
from clickhouse_driver import Client as Clickhouse

# query_time = Summary("query", "query", ["hash", ], registry=metrics.registry)
Base = declarative_base()


def _gen_application_name():  # pragma: no cover
    try:
        machine_id = "/etc/machine-id"
        with open(machine_id) as fd:
            mid = fd.read(8)

    except FileNotFoundError:
        mid = "macos"

    pid = os.getpid()
    return f"api-{mid}-{pid}"


def query_hash(q: str) -> str:
    """Short hash used to identify query statements.
    Allows correlating query statements between API logs and metrics
    """
    return shake_128(q.encode()).hexdigest(4)


# # Clickhouse


def init_clickhouse_db(app) -> None:
    """Initializes Clickhouse session"""
    url = app.config["CLICKHOUSE_URL"]
    app.logger.info("Connecting to Clickhouse")
    app.click = Clickhouse.from_url(url)


Query = Union[str, TextClause, Select]


def _run_query(query: Query, query_params: dict):
    if isinstance(query, (Select, TextClause)):
        query = str(query.compile(dialect=postgresql.dialect()))
    q = current_app.click.execute(query, query_params, with_column_types=True)
    rows, coldata = q
    colnames, coltypes = tuple(zip(*coldata))
    return colnames, rows


def query_click(query: Query, query_params: dict) -> List[Dict]:
    colnames, rows = _run_query(query, query_params)
    return [dict(zip(colnames, row)) for row in rows]


def query_click_one_row(query: Query, query_params: dict) -> Optional[dict]:
    colnames, rows = _run_query(query, query_params)
    for row in rows:
        return dict(zip(colnames, row))

    return None


def insert_click(query, rows: list) -> int:
    assert isinstance(rows, list)
    return current_app.click.execute(query, rows, types_check=True)
