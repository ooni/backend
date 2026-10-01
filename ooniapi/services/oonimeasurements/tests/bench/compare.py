"""
Compare two benchmark result files written with OONI_BENCH_JSON.

    python -m tests.bench.compare baseline.json candidate.json [--markdown] [--summary-file F]

Each side may be several comma separated runs, for example interleaved
base,head,base,head rounds: each query then takes its fastest median, so load
that slows one round does not favour either side. Pass "-" as baseline to
report the candidate alone. A differing response hash
means the candidate changed an endpoint's output on the same dataset, which a
performance change must never do: the exit status is 1 in that case.

Bytes read is deterministic for a given dataset and, unlike rows read, also
reflects how many columns a query reads, so it is what changes are judged on;
wall clock time is reported for information only.
"""

import argparse
import json
import sys

# bytes read ratios outside this band count as a change
THRESHOLD = 0.10


def load(paths):
    if paths == "-":
        return None
    runs = []
    for path in paths.split(","):
        with open(path) as f:
            runs.append(json.load(f))
    merged = runs[0]
    for run in runs[1:]:
        for kind, key in (("queries", "median_ms"), ("ingest", "p50_ms")):
            for name, result in run[kind].items():
                if name in merged[kind] and result[key] < merged[kind][name][key]:
                    merged[kind][name] = result
    return merged


def drift(rows):
    """Median time ratio of queries whose bytes read did not change.

    Their speed cannot have changed because of the candidate, so this measures
    how much the runs differ by themselves."""
    ratios = sorted(
        r["new"]["median_ms"] / r["base"]["median_ms"]
        for r in rows
        if r["base"] and r["new"] and r["base"]["median_ms"]
        and r["base"]["read_bytes"] == r["new"]["read_bytes"]
    )
    return ratios[len(ratios) // 2] if ratios else None


def compare(baseline, candidate):
    rows = []
    base_q = baseline["queries"] if baseline else {}
    for name in sorted(set(base_q) | set(candidate["queries"])):
        b, c = base_q.get(name), candidate["queries"].get(name)
        row = {"name": name, "base": b, "new": c, "verdict": "new" if not b else "removed" if not c else ""}
        if b and c:
            ratio = c["read_bytes"] / b["read_bytes"] if b["read_bytes"] else 1.0
            row["bytes_ratio"] = ratio
            if b["response_hash"] != c["response_hash"]:
                row["verdict"] = "RESPONSE CHANGED"
            elif ratio < 1 - THRESHOLD:
                row["verdict"] = "reads less"
            elif ratio > 1 + THRESHOLD:
                row["verdict"] = "reads more"
        rows.append(row)
    return rows


def summary(rows, has_baseline):
    if not has_baseline:
        return f"{len(rows)} queries benchmarked, no baseline to compare with"
    count = lambda v: sum(r["verdict"] == v for r in rows)
    changed = count("RESPONSE CHANGED")
    text = f"{count('reads less')} of {len(rows)} queries read less, {count('reads more')} more"
    return f"{changed} RESPONSES CHANGED; {text}" if changed else f"responses unchanged; {text}"


def _ms(r):
    return f"{r['median_ms']:.1f}" if r else ""


def _rows(r):
    return f"{r['read_rows']:,}" if r else ""


def _mb(r):
    return f"{r['read_bytes'] / 1e6:.1f}" if r else ""


def render_text(rows, baseline, candidate):
    lines = [f"{'query':<45} {'base ms':>9} {'new ms':>9} {'base MB':>9} {'new MB':>9} {'base rows':>12} {'new rows':>12}  verdict"]
    for r in rows:
        lines.append(
            f"{r['name']:<45} {_ms(r['base']):>9} {_ms(r['new']):>9} {_mb(r['base']):>9} {_mb(r['new']):>9}"
            f" {_rows(r['base']):>12} {_rows(r['new']):>12}  {r['verdict']}"
        )
    lines += [f"{name:<45} {_ingest(baseline, candidate, name)}" for name in sorted(candidate["ingest"])]
    return "\n".join(lines)


def render_markdown(rows, baseline, candidate):
    lines = [
        f"**{summary(rows, baseline is not None)}**",
        "",
        f"dataset `{candidate['meta']['dataset']}`, git `{candidate['meta']['git']}`"
        + (f", baseline git `{baseline['meta']['git']}`" if baseline else ""),
        "",
    ]
    d = drift(rows)
    if d is not None:
        lines += [
            f"Time is informational: queries whose bytes read did not change ran x{d:.2f} on median,"
            " which is the run to run noise; bytes read is deterministic.",
            "",
        ]
    lines += [
        "| query | base ms | new ms | base MB read | new MB read | base rows | new rows | |",
        "|---|--:|--:|--:|--:|--:|--:|---|",
    ]
    lines += [
        f"| {r['name']} | {_ms(r['base'])} | {_ms(r['new'])} | {_mb(r['base'])} | {_mb(r['new'])}"
        f" | {_rows(r['base'])} | {_rows(r['new'])} | {r['verdict']} |"
        for r in rows
    ]
    if candidate["ingest"]:
        lines += ["", "| ingest | per insert |", "|---|---|"]
        lines += [f"| {name} | {_ingest(baseline, candidate, name)} |" for name in sorted(candidate["ingest"])]
    return "\n".join(lines)


def _ingest(baseline, candidate, name):
    c = candidate["ingest"][name]
    b = (baseline or {}).get("ingest", {}).get(name)
    fields = [("p50_ms", "p50 {} ms"), ("files_opened", "files {}"), ("bytes_written", "written {} B"), ("cpu_us", "cpu {} us")]
    return ", ".join(fmt.format(f"{b[k]} -> {c[k]}" if b else c[k]) for k, fmt in fields)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--summary-file", help="write the one line summary here")
    args = parser.parse_args(argv)

    baseline, candidate = load(args.baseline), load(args.candidate)
    if baseline and baseline["meta"]["dataset"] != candidate["meta"]["dataset"]:
        print(f"warning: datasets differ: {baseline['meta']['dataset']} vs {candidate['meta']['dataset']}", file=sys.stderr)
    rows = compare(baseline, candidate)
    render = render_markdown if args.markdown else render_text
    print(render(rows, baseline, candidate))
    if args.summary_file:
        with open(args.summary_file, "w") as f:
            f.write(summary(rows, baseline is not None))
    return 1 if any(r["verdict"] == "RESPONSE CHANGED" for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
