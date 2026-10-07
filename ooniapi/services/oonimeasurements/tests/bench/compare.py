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
# time is noisy even after correcting for drift: note only large changes
TIME_THRESHOLD = 0.25
TIME_FLOOR_MS = 2.0
DOWN, UP, DOT = "\u2193", "\u2191", "\u00b7"
# arrow colors by size of change, from GitHub's palette, for factors from 1.1
# (THRESHOLD) up to 1.5, 2, 4, 8 and beyond: the larger the saving, the
# brighter the green; the larger the regression, the deeper the red
SHADE_FACTORS = (1.5, 2, 4, 8)
LESS_SHADES = ("#116329", "#1a7f37", "#2da44e", "#4ac26b", "#6fdd8b")
MORE_SHADES = ("#d4a72c", "#bc4c00", "#cf222e", "#a40e26", "#82071e")


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
            if b["read_bytes"]:
                ratio = c["read_bytes"] / b["read_bytes"]
            else:
                # nothing read on the base: any read now is more, not unchanged
                ratio = float("inf") if c["read_bytes"] else 1.0
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


def _arrow(less, factor, plain):
    """A down or up arrow, colored by the size of the change unless plain.
    Markdown cannot color text, so the color comes from GitHub's math."""
    if plain:
        return DOWN if less else UP
    shades = LESS_SHADES if less else MORE_SHADES
    shade = shades[sum(factor >= f for f in SHADE_FACTORS)]
    glyph = "\\blacktriangledown" if less else "\\blacktriangle"
    return f"$`\\color{{{shade}}}{glyph}`$"


def _factor(base, new):
    return base / new if new < base else new / base


def _change_note(r, d, plain):
    """Arrow, factor and bar for a significant change in bytes read, and a
    note for a significant change in time, after correcting for drift."""
    b, c = r["base"], r["new"]
    if not (b and c):
        return ""
    notes = []
    if b["read_bytes"] and c["read_bytes"] and abs(c["read_bytes"] / b["read_bytes"] - 1) >= THRESHOLD:
        f = _factor(b["read_bytes"], c["read_bytes"])
        less = c["read_bytes"] < b["read_bytes"]
        word = "less" if less else "more"
        notes.append(f"{_arrow(less, f, plain)} {f:.1f}x {word} read")
    elif bool(b["read_bytes"]) != bool(c["read_bytes"]):
        less = not c["read_bytes"]
        notes.append(f"{_arrow(less, SHADE_FACTORS[-1], plain)} {'reads nothing' if less else 'reads where base read nothing'}")
    base_ms, new_ms = b["median_ms"] * (d or 1), c["median_ms"]
    if base_ms and abs(new_ms - base_ms) >= TIME_FLOOR_MS and abs(new_ms / base_ms - 1) >= TIME_THRESHOLD:
        notes.append(f"{_factor(base_ms, new_ms):.1f}x {'faster' if new_ms < base_ms else 'slower'}")
    return f" {DOT} ".join(notes)


def render_markdown(rows, baseline, candidate, plain=False):
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
        f" | {_rows(r['base'])} | {_rows(r['new'])} | {' '.join(x for x in (r['verdict'] if r['verdict'] == 'RESPONSE CHANGED' else '', _change_note(r, d, plain) or r['verdict']) if x)} |"
        for r in rows
    ]
    if baseline:
        lines += [
            "",
            f"{_arrow(True, 4, plain)} / {_arrow(False, 4, plain)}: bytes read went down / up by at least"
            f" {THRESHOLD:.0%}" + ("" if plain else "; the larger the change, the brighter the green or the deeper the red")
            + f". Time is noted when it changed by at least {TIME_THRESHOLD:.0%} after correcting for drift.",
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
    parser.add_argument("--plain", action="store_true", help="markdown without colored arrows")
    parser.add_argument("--summary-file", help="write the one line summary here")
    args = parser.parse_args(argv)

    baseline, candidate = load(args.baseline), load(args.candidate)
    if baseline and baseline["meta"]["dataset"] != candidate["meta"]["dataset"]:
        print(f"warning: datasets differ: {baseline['meta']['dataset']} vs {candidate['meta']['dataset']}", file=sys.stderr)
    rows = compare(baseline, candidate)
    if args.markdown:
        print(render_markdown(rows, baseline, candidate, args.plain))
    else:
        print(render_text(rows, baseline, candidate))
    if args.summary_file:
        with open(args.summary_file, "w") as f:
            f.write(summary(rows, baseline is not None))
    return 1 if any(r["verdict"] == "RESPONSE CHANGED" for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
