"""
Benchmark fixtures.

Environment variables:
    OONI_BENCH_ROWS             fastpath rows to generate (default 50000); obs_web
                                gets 3x, analysis_web_measurement 0.7x
    OONI_BENCH_REPS             timed repetitions per request (default 3)
    OONI_BENCH_JSON             write results to this path, for bench/compare.py
    OONI_BENCH_CLICKHOUSE_URL   run against an existing database (e.g. a replica
                                with real data) instead of generating one; it is
                                only read from, and ingest benchmarks are skipped
"""

import hashlib
import json
import os
import statistics
import subprocess
import time
from datetime import date, datetime, time as dt_time, timezone
from unittest.mock import patch

import pytest
from clickhouse_driver import Client as ClickhouseClient
from fastapi.testclient import TestClient
from freezegun import freeze_time

from oonimeasurements.common.dependencies import get_settings
from oonimeasurements.main import create_app, setup_router

from ..conftest import make_override_get_settings
from . import synthetic

BENCH_DB = "ooni_bench"
ROWS = int(os.environ.get("OONI_BENCH_ROWS", 50_000))
REPS = int(os.environ.get("OONI_BENCH_REPS", 3))
EXTERNAL_URL = os.environ.get("OONI_BENCH_CLICKHOUSE_URL")
HARNESS = {"log_comment": "ooni-bench-harness"}
VOLATILE_KEYS = {"db_stats", "query_time", "elapsed_seconds"}
# endpoints derive default windows from the wall clock; pin it so that runs
# made at different times of the same day return identical responses
ANCHOR = datetime.combine(date.today(), dt_time(12), tzinfo=timezone.utc)


def _dataset_id() -> str:
    return f"rows={ROWS} days={synthetic.DAYS} anchor={date.today()} schema={synthetic.schema_fingerprint()}"


def _is_current(click) -> bool:
    try:
        rows = click.execute(f"SELECT dataset_id FROM {BENCH_DB}.bench_meta", settings=HARNESS)
    except Exception:
        return False
    return rows == [(_dataset_id(),)]


def _build(server_url: str):
    with ClickhouseClient.from_url(server_url) as click:
        if _is_current(click):
            return
        click.execute(f"DROP DATABASE IF EXISTS {BENCH_DB} SYNC")
        click.execute(f"CREATE DATABASE {BENCH_DB}")
    with ClickhouseClient.from_url(f"{server_url}/{BENCH_DB}") as click:
        synthetic.create_schema(click)
        synthetic.populate(click, ROWS)
        click.execute("CREATE TABLE bench_meta (dataset_id String) ENGINE = TinyLog")
        click.execute("INSERT INTO bench_meta VALUES", [(_dataset_id(),)])


@pytest.fixture(scope="session")
def bench_db(request):
    if EXTERNAL_URL:
        return EXTERNAL_URL
    server_url = request.getfixturevalue("clickhouse_server")
    _build(server_url)
    return f"{server_url}/{BENCH_DB}"


@pytest.fixture(scope="session")
def bench_writable():
    if EXTERNAL_URL:
        pytest.skip("ingest benchmarks never write to an external database")


@pytest.fixture(scope="session")
def bench_client(bench_db):
    app = create_app()
    override = make_override_get_settings(
        clickhouse_url=bench_db,
        jwt_encryption_key="super_secure",
        prometheus_metrics_password="super_secure",
        account_id_hashing_key="super_secure",
    )
    with patch("oonimeasurements.common.dependencies.get_settings") as mocked_gs:
        mocked_gs.return_value = override()
        app.dependency_overrides[get_settings] = override
        setup_router(app)
        yield TestClient(app)


def _stable_hash(body) -> str:
    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k not in VOLATILE_KEYS}
        if isinstance(o, list):
            return [strip(v) for v in o]
        return o

    return hashlib.sha256(json.dumps(strip(body), sort_keys=True).encode()).hexdigest()[:16]


class Recorder:
    def __init__(self):
        self.queries = {}
        self.ingest = {}

    def query(self, client, name, path, params=None):
        """Time `path` and return its (last) response body.

        Server side cost is read from system.query_log, so it covers every
        query the endpoint issues for one request.
        """
        with freeze_time(ANCHOR, tick=True):
            return self._query(client, name, path, params)

    def _query(self, client, name, path, params):
        response = client.get(path, params=params)  # warm up caches
        assert response.status_code == 200, f"{name}: {response.text[:500]}"
        [(start,)] = self.click.execute("SELECT toUnixTimestamp64Micro(now64(6))", settings=HARNESS)
        timings = []
        for _ in range(REPS):
            t0 = time.perf_counter()
            response = client.get(path, params=params)
            timings.append(time.perf_counter() - t0)
            assert response.status_code == 200, f"{name}: {response.text[:500]}"
        body = response.json()
        read_rows, read_bytes = self._server_cost(start)
        self.queries[name] = {
            "path": path,
            "params": params,
            "median_ms": round(statistics.median(timings) * 1000, 2),
            "read_rows": read_rows // REPS,
            "read_bytes": read_bytes // REPS,
            "response_hash": _stable_hash(body),
        }
        return body

    def _server_cost(self, start):
        self.click.execute("SYSTEM FLUSH LOGS", settings=HARNESS)
        [(rows, nbytes)] = self.click.execute(
            """
            SELECT sum(read_rows), sum(read_bytes) FROM system.query_log
            WHERE type = 'QueryFinish' AND toUnixTimestamp64Micro(query_start_time_microseconds) >= %(start)s
              AND user = currentUser() AND log_comment != %(harness)s
              AND is_initial_query
            """,
            {"start": start, "harness": HARNESS["log_comment"]},
            settings=HARNESS,
        )
        return int(rows), int(nbytes)

    def report(self):
        return {
            "meta": {
                "dataset": EXTERNAL_URL and "external" or _dataset_id(),
                "reps": REPS,
                "git": _git_describe(),
            },
            "queries": self.queries,
            "ingest": self.ingest,
        }


def _git_describe():
    try:
        return subprocess.check_output(
            ["git", "describe", "--always", "--dirty"], text=True, cwd=synthetic.TESTS_DIR
        ).strip()
    except Exception:
        return None


_recorder = Recorder()


@pytest.fixture(scope="session")
def bench(bench_db):
    with ClickhouseClient.from_url(bench_db) as click:
        _recorder.click = click
        yield _recorder
    path = os.environ.get("OONI_BENCH_JSON")
    if path:
        with open(path, "w") as out:
            json.dump(_recorder.report(), out, indent=2, sort_keys=True, default=str)


def pytest_terminal_summary(terminalreporter):
    if not (_recorder.queries or _recorder.ingest):
        return
    tr = terminalreporter
    tr.section(f"ooni benchmarks ({_dataset_id() if not EXTERNAL_URL else 'external'})")
    for name, r in sorted(_recorder.queries.items()):
        tr.write_line(f"{name:<55} {r['median_ms']:>10.1f} ms {r['read_rows']:>12} rows")
    for name, r in sorted(_recorder.ingest.items()):
        tr.write_line(f"{name:<55} p50 {r['p50_ms']:>7.2f} ms  p95 {r['p95_ms']:>7.2f} ms")
