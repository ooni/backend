"""
Ingest benchmarks for the tables on the measurement write path.

The fastpath inserts one row per measurement (about 38 inserts/s in
production), so per-insert latency of small batches is what matters: an index
or projection that slows these down can make the fastpath drop measurements.
Each run inserts into an empty clone of the table, which keeps every index and
projection of the original.
"""

import os
import statistics
import time

import pytest

INSERTS = int(os.environ.get("OONI_BENCH_INSERTS", 100))

CASES = {
    "ingest.fastpath.batch_1": ("fastpath", 1),
    "ingest.fastpath.batch_100": ("fastpath", 100),
    "ingest.obs_web.batch_4": ("obs_web", 4),
    "ingest.obs_web.batch_100": ("obs_web", 100),
    "ingest.analysis_web_measurement.batch_1": ("analysis_web_measurement", 1),
}


@pytest.mark.parametrize("name", CASES)
def test_bench_ingest(bench, bench_writable, name):
    table, batch = CASES[name]
    clone = f"bench_ingest_{table}"
    click = bench.click
    click.execute(f"DROP TABLE IF EXISTS {clone} SYNC")
    click.execute(f"CREATE TABLE {clone} AS {table}")
    try:
        columns = _insertable_columns(click, table)
        rows = click.execute(
            f"SELECT {','.join(columns)} FROM {table} ORDER BY measurement_start_time DESC LIMIT {INSERTS * batch}"
        )
        insert = f"INSERT INTO {clone} ({','.join(columns)}) VALUES"
        tag = {"log_comment": f"ooni-bench-{name}"}
        timings = []
        for i in range(INSERTS):
            chunk = rows[i * batch:(i + 1) * batch]
            t0 = time.perf_counter()
            click.execute(insert, chunk, settings=tag)
            timings.append(time.perf_counter() - t0)
        cost = _server_cost(click, tag["log_comment"])
        [(count,)] = click.execute(f"SELECT count() FROM {clone}")
        assert count == len(rows)
    finally:
        click.execute(f"DROP TABLE IF EXISTS {clone} SYNC")

    timings.sort()
    bench.ingest[name] = {
        "batch": batch,
        "inserts": INSERTS,
        "p50_ms": round(statistics.median(timings) * 1000, 3),
        "p95_ms": round(timings[int(len(timings) * 0.95) - 1] * 1000, 3),
        "mean_ms": round(statistics.fmean(timings) * 1000, 3),
        **cost,
    }


def _server_cost(click, log_comment):
    # deterministic per insert costs, unlike wall clock time on a shared host
    click.execute("SYSTEM FLUSH LOGS")
    [(files, written, cpu_us)] = click.execute(
        """
        SELECT
            avg(ProfileEvents['FileOpen']),
            avg(ProfileEvents['WriteBufferFromFileDescriptorWriteBytes']),
            avg(ProfileEvents['UserTimeMicroseconds'] + ProfileEvents['SystemTimeMicroseconds'])
        FROM system.query_log
        WHERE type = 'QueryFinish' AND log_comment = %(c)s AND query_kind = 'Insert'
          AND event_date >= yesterday()
        """,
        {"c": log_comment},
    )
    return {"files_opened": round(files, 1), "bytes_written": round(written), "cpu_us": round(cpu_us)}


def _insertable_columns(click, table):
    rows = click.execute(
        "SELECT name FROM system.columns WHERE database = currentDatabase() AND table = %(t)s"
        " AND default_kind NOT IN ('MATERIALIZED', 'ALIAS') ORDER BY position",
        {"t": table},
    )
    return [name for (name,) in rows]
