"""
How many fastpath granules a lookup by measurement_uid or report_id selects,
with the skip indexes alone and with a measurement_start_time window around
the timestamp the id starts with.

Only EXPLAIN is run for the lookups, so this is cheap and read-only and can be
pointed at production:

    python tests/bench/lookup_pruning.py clickhouse://user:pass@host:9000/ooni
    python tests/bench/lookup_pruning.py clickhouse://test:test@localhost:9000/ooni_bench
"""

import argparse
import statistics
from datetime import datetime, timedelta

from clickhouse_driver import Client

# first windows of the lookup cascade, from production data2 (2026-10)
UID_WINDOW = (timedelta(minutes=15), timedelta(minutes=15))
REPORT_WINDOW = (timedelta(minutes=15), timedelta(hours=2))


def granules(click, query):
    """Granules left after the last index EXPLAIN reports."""
    selected = None
    for (line,) in click.execute(f"EXPLAIN indexes = 1 {query}"):
        line = line.strip()
        if line.startswith("Granules:"):
            selected = int(line.split()[1].split("/")[0])
    return selected


def window(t, around):
    before, after = around
    return f" AND measurement_start_time BETWEEN '{t - before}' AND '{t + after}'"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--days", type=int, default=7, help="sample measurements from the last DAYS days")
    args = parser.parse_args(argv)

    click = Client.from_url(args.url)
    [(total,)] = click.execute("SELECT sum(marks) FROM system.parts WHERE database = currentDatabase() AND table = 'fastpath' AND active")
    sample = click.execute(
        "SELECT measurement_uid, report_id, input FROM fastpath"
        f" WHERE measurement_start_time >= now() - INTERVAL {args.days} DAY"
        f" ORDER BY cityHash64(measurement_uid) LIMIT {args.samples}"
    )
    results = {"uid, skip index": [], "uid, time window": [], "report_id, skip index": [], "report_id, time window": []}
    for uid, report_id, input_ in sample:
        by_uid = f"SELECT * FROM fastpath WHERE measurement_uid = '{uid}'"
        by_report = f"SELECT * FROM fastpath WHERE report_id = '{report_id}' AND input = '{input_.replace(chr(39), chr(92) + chr(39))}'"
        collected = datetime.strptime(uid[:14], "%Y%m%d%H%M%S")
        opened = datetime.strptime(report_id[:16], "%Y%m%dT%H%M%SZ")
        results["uid, skip index"].append(granules(click, by_uid))
        results["uid, time window"].append(granules(click, by_uid + window(collected, UID_WINDOW)))
        results["report_id, skip index"].append(granules(click, by_report))
        results["report_id, time window"].append(granules(click, by_report + window(opened, REPORT_WINDOW)))

    print(f"fastpath: {total:,} granules; {len(sample)} random measurements from the last {args.days} days")
    print(f"{'lookup':<24} {'median granules':>16} {'p90':>8} {'max':>8}")
    for name, values in results.items():
        values = sorted(values)
        p90 = values[int(len(values) * 0.9) - 1] if values else 0
        print(f"{name:<24} {statistics.median(values):>16,.0f} {p90:>8,} {values[-1]:>8,}")


if __name__ == "__main__":
    main()
