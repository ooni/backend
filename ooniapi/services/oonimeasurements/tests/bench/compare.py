"""
Compare two benchmark result files written with OONI_BENCH_JSON.

    python -m tests.bench.compare baseline.json candidate.json

A differing response hash means the candidate changed an endpoint's output on
the same dataset, which a performance change must never do.
"""

import json
import sys


def main(baseline_path, candidate_path):
    baseline, candidate = (json.load(open(p)) for p in (baseline_path, candidate_path))
    if baseline["meta"]["dataset"] != candidate["meta"]["dataset"]:
        print(f"warning: datasets differ\n  {baseline['meta']['dataset']}\n  {candidate['meta']['dataset']}")

    changed = []
    print(f"{'query':<55} {'base ms':>9} {'new ms':>9} {'speedup':>8} {'base rows':>11} {'new rows':>11}")
    for name in sorted(set(baseline["queries"]) | set(candidate["queries"])):
        b, c = baseline["queries"].get(name), candidate["queries"].get(name)
        if not (b and c):
            print(f"{name:<55} {'only in ' + ('baseline' if b else 'candidate'):>30}")
            continue
        speedup = b["median_ms"] / c["median_ms"] if c["median_ms"] else float("inf")
        same = b["response_hash"] == c["response_hash"]
        changed += [] if same else [name]
        print(
            f"{name:<55} {b['median_ms']:>9.1f} {c['median_ms']:>9.1f} {speedup:>7.2f}x"
            f" {b['read_rows']:>11} {c['read_rows']:>11}{'' if same else '  RESPONSE CHANGED'}"
        )

    for name in sorted(set(baseline["ingest"]) & set(candidate["ingest"])):
        b, c = baseline["ingest"][name], candidate["ingest"][name]
        print(
            f"{name:<55} p50 {b['p50_ms']:.2f} -> {c['p50_ms']:.2f} ms, p95 {b['p95_ms']:.2f} -> {c['p95_ms']:.2f} ms,"
            f" files {b['files_opened']} -> {c['files_opened']}, written {b['bytes_written']} -> {c['bytes_written']} B,"
            f" cpu {b['cpu_us']} -> {c['cpu_us']} us"
        )

    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
