import os
import re
import sqlite3
import tempfile
import pytest

from fastapi.testclient import TestClient

from ..dependencies import get_clickhouse_client
from ..main import app

THIS_DIR = os.path.dirname(__file__)


@pytest.fixture(name="clickhouse")
def clickhouse_fixture():
    fd, path = tempfile.mkstemp()
    print(f"created sqlite file {path}")

    conn = sqlite3.connect(path, check_same_thread=False)

    statements = []
    for fn in ["1_schema.sql", "2_fastpath_fixtures.sql"]:
        with open(os.path.join(THIS_DIR, "fixtures", fn)) as in_file:
            sql = in_file.read()
        statements += sql.split(";")
    cur = conn.cursor()
    for statement in statements:
        if statement.strip():
            cur.execute(statement)
    conn.commit()

    def replace_template_params(sql):
        sql = re.sub(r"%\((.+?)\)s", r":\1", sql)
        return sql

    class MockClick:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, sql, query_params=(), *arg, **kwargs):
            cursor = conn.cursor()
            sql = replace_template_params(sql)
            cursor.execute(sql, query_params)
            rows = cursor.fetchall()
            colnames = [description[0] for description in cursor.description]
            return rows, [(cn, None) for cn in colnames]

    yield MockClick(conn)
    conn.close()
    os.close(fd)
    os.remove(path)


@pytest.fixture(name="client")
def client_fixture(clickhouse):
    def get_clickhouse_override():
        return clickhouse

    app.dependency_overrides[get_clickhouse_client] = get_clickhouse_override

    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_list_measurements(client, clickhouse):
    response = client.get("/api/v1/measurements?since=2024-01-01&until=2024-02-01")
    assert response.status_code == 200
    j = response.json()
    assert len(j["results"]) == 100

    response = client.get(
        "/api/v1/measurements?probe_cc=IT&since=2024-01-01&until=2024-02-01"
    )
    assert response.status_code == 200
    j = response.json()
    for res in j["results"]:
        assert res["probe_cc"] == "IT"

    app.dependency_overrides.clear()
