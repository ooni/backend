"""
Query benchmarks for every oonimeasurements endpoint that reads ClickHouse.

Not covered:
    /api/v1/torsf_stats                         broken on master
    /api/v1/raw_measurement                     reads measurement bodies from S3
    /api/v1/aggregation/observations/ctrl       obs_web_ctrl is not in the test schema
"""

import json
from datetime import timedelta

import pytest

from .conftest import VOLATILE_KEYS
from .synthetic import ANCHOR_DATE, TODAY, country_asn

CC = "US"
# the busiest US network
ASN = country_asn(CC)
DOMAIN = "site0.example.org"
# production's costliest search (data2, 2026-10: 40% of query time): pollers
# checking whether IPs, which are never an input, are measured from IR
ABSENT_CC = "IR"
ABSENT_INPUT = "95.179.192.8"


def ago(days: int) -> str:
    return (ANCHOR_DATE - timedelta(days=days)).isoformat()


LAST_30 = {"since": ago(30), "until": ago(0)}

CASES = {
    # /api/v1/aggregation
    "aggregation.no_axis.cc": ("/api/v1/aggregation", {"probe_cc": CC, **LAST_30}),
    "aggregation.no_axis.cc.default_window": ("/api/v1/aggregation", {"probe_cc": CC}),
    "aggregation.x_day.cc": ("/api/v1/aggregation", {"probe_cc": CC, "axis_x": "measurement_start_day", **LAST_30}),
    "aggregation.x_day.hour.7d": ("/api/v1/aggregation", {"axis_x": "measurement_start_day", "since": ago(7), "until": ago(0)}),
    "aggregation.x_day.y_cc.week.180d": (
        "/api/v1/aggregation",
        {"axis_x": "measurement_start_day", "axis_y": "probe_cc", "time_grain": "week", "since": ago(180), "until": ago(0)},
    ),
    "aggregation.x_cc": ("/api/v1/aggregation", {"axis_x": "probe_cc", **LAST_30}),
    "aggregation.x_domain.cc": ("/api/v1/aggregation", {"axis_x": "domain", "probe_cc": CC, "test_name": "web_connectivity", **LAST_30}),
    "aggregation.x_blocking_type": ("/api/v1/aggregation", {"axis_x": "blocking_type", **LAST_30}),
    "aggregation.x_day.category_code.cc": (
        "/api/v1/aggregation",
        {"axis_x": "measurement_start_day", "category_code": "NEWS", "probe_cc": CC, **LAST_30},
    ),
    "aggregation.cc.input": ("/api/v1/aggregation", {"probe_cc": CC, "input": "{busiest_input}", **LAST_30}),
    "aggregation.cc.input_absent": ("/api/v1/aggregation", {"probe_cc": ABSENT_CC, "input": ABSENT_INPUT, **LAST_30}),
    "aggregation.x_cc.domain.180d": ("/api/v1/aggregation", {"axis_x": "probe_cc", "domain": DOMAIN, "since": ago(180), "until": ago(0)}),
    # /api/v1/measurements, /api/v1/measurement_meta
    "measurements.default": ("/api/v1/measurements", {}),
    "measurements.cc": ("/api/v1/measurements", {"probe_cc": CC}),
    "measurements.cc.anomaly": ("/api/v1/measurements", {"probe_cc": CC, "anomaly": "true"}),
    "measurements.domain": ("/api/v1/measurements", {"domain": DOMAIN}),
    "measurements.report_id": ("/api/v1/measurements", {"report_id": "{report_id}"}),
    "measurements.cc.input_absent.7d": (
        "/api/v1/measurements", {"probe_cc": ABSENT_CC, "input": ABSENT_INPUT, "since": ago(7), "until": ago(0)},
    ),
    "measurements.cc.input_absent.30d": ("/api/v1/measurements", {"probe_cc": ABSENT_CC, "input": ABSENT_INPUT}),
    "measurements.cc.test.anomaly": (
        "/api/v1/measurements", {"probe_cc": CC, "test_name": "web_connectivity", "anomaly": "true"},
    ),
    "measurement_meta.uid": ("/api/v1/measurement_meta", {"measurement_uid": "{measurement_uid}"}),
    "measurement_meta.report_id": ("/api/v1/measurement_meta", {"report_id": "{report_id}", "input": "{input}"}),
    # /api/v1/observations, /api/v1/aggregation/observations
    "observations.default": ("/api/v1/observations", {}),
    "observations.cc": ("/api/v1/observations", {"probe_cc": CC}),
    "observations.2d": ("/api/v1/observations", {"since": ago(3), "until": ago(1)}),
    "observations.report_id": ("/api/v1/observations", {"report_id": "{obs_report_id}"}),
    "aggregation_observations.default": ("/api/v1/aggregation/observations", {}),
    "aggregation_observations.cc.timestamp": (
        "/api/v1/aggregation/observations",
        {"probe_cc": CC, "group_by": ["failure", "timestamp"]},
    ),
    "aggregation_observations.hostname": ("/api/v1/aggregation/observations", {"hostname": DOMAIN}),
    # /api/v1/analysis, /api/v1/aggregation/analysis, /api/v1/detector/changepoints
    "analysis.default": ("/api/v1/analysis", {}),
    "analysis.cc": ("/api/v1/analysis", {"probe_cc": CC}),
    "aggregation_analysis.default": ("/api/v1/aggregation/analysis", {}),
    "aggregation_analysis.cc": ("/api/v1/aggregation/analysis", {"probe_cc": CC}),
    "aggregation_analysis.x_domain.cc": ("/api/v1/aggregation/analysis", {"axis_x": "domain", "probe_cc": CC}),
    "changepoints.default": ("/api/v1/detector/changepoints", {}),
    "changepoints.cc": ("/api/v1/detector/changepoints", {"probe_cc": CC}),
    # /api/_/ private endpoints used by Explorer
    "private.asn_by_month": ("/api/_/asn_by_month", {}),
    "private.countries_by_month": ("/api/_/countries_by_month", {}),
    "private.countries": ("/api/_/countries", {}),
    "private.test_coverage": ("/api/_/test_coverage", {"probe_cc": CC}),
    "private.website_networks": ("/api/_/website_networks", {"probe_cc": CC}),
    "private.website_stats": ("/api/_/website_stats", {"probe_cc": CC, "probe_asn": "{busiest_asn}", "input": "{busiest_input}"}),
    "private.website_urls": ("/api/_/website_urls", {"probe_cc": CC, "probe_asn": f"AS{ASN}"}),
    "private.vanilla_tor_stats": ("/api/_/vanilla_tor_stats", {"probe_cc": CC}),
    "private.im_networks": ("/api/_/im_networks", {"probe_cc": CC}),
    "private.im_stats": ("/api/_/im_stats", {"probe_cc": CC, "probe_asn": f"AS{ASN}", "test_name": "signal"}),
    "private.country_overview": ("/api/_/country_overview", {"probe_cc": CC}),
    "private.global_overview": ("/api/_/global_overview", {}),
    "private.global_overview_by_month": ("/api/_/global_overview_by_month", {}),
    "private.circumvention_stats_by_country": ("/api/_/circumvention_stats_by_country", {}),
    "private.circumvention_runtime_stats": ("/api/_/circumvention_runtime_stats", {}),
    "private.domain_metadata": ("/api/_/domain_metadata", {"domain": DOMAIN}),
    "private.asnmeta": ("/api/_/asnmeta", {"asn": ASN}),
    "private.networks": ("/api/_/networks", {}),
    "private.domains": ("/api/_/domains", {}),
}


@pytest.fixture(scope="session")
def samples(bench):
    [(report_id, measurement_uid, input)] = bench.click.execute(
        f"SELECT report_id, measurement_uid, input FROM fastpath WHERE probe_cc = '{CC}' AND test_name = 'web_connectivity'"
        f" AND measurement_start_time >= {TODAY} - 7 ORDER BY measurement_uid LIMIT 1"
    )
    [(obs_report_id,)] = bench.click.execute(
        f"SELECT report_id FROM obs_web WHERE measurement_start_time >= {TODAY} - 7 ORDER BY measurement_uid LIMIT 1"
    )
    [(busiest_asn, busiest_input)] = bench.click.execute(
        f"SELECT probe_asn, input FROM fastpath WHERE probe_cc = '{CC}' AND test_name = 'web_connectivity'"
        f" AND measurement_start_time >= {TODAY} - 30 GROUP BY probe_asn, input ORDER BY count() DESC, probe_asn, input LIMIT 1"
    )
    return {
        "report_id": report_id,
        "measurement_uid": measurement_uid,
        "input": input,
        "obs_report_id": obs_report_id,
        "busiest_asn": str(busiest_asn),
        "busiest_input": busiest_input,
    }


def _has_data(body) -> bool:
    if isinstance(body, list):
        return len(body) > 0
    if isinstance(body, dict):
        return any(_has_data(v) for k, v in body.items() if k != "metadata" and k not in VOLATILE_KEYS)
    if isinstance(body, bool):
        return body
    if isinstance(body, (int, float)):
        return body > 0
    return bool(body)


# cases that must find nothing, like their production counterparts
EMPTY = {"measurements.cc.input_absent.7d", "measurements.cc.input_absent.30d", "aggregation.cc.input_absent"}


# endpoints whose SQL has no ORDER BY, or orders with ties (im_networks:
# networks with the same count): the order of their results depends on the
# query plan, so a change of plan must not count as a changed response
UNORDERED = {
    "private.networks", "changepoints.default", "changepoints.cc", "private.im_networks",
    # ordered by timestamp and count, with ties
    "aggregation_observations.default", "aggregation_observations.cc.timestamp",
    "aggregation_observations.hostname",
}


def _counts_only(body):
    # quantile() samples groups of more than 8192 values, nondeterministically
    # across threads: at 120M rows the p50 and p90 of a group differ from one
    # run to the next (5 runs, 5 results) while the counts do not
    return [{**r, "v": r["v"][2:]} for r in body["results"]]


def _defined_order(body):
    # ORDER BY measurement_start_time DESC LIMIT leaves rows with the same
    # time in no defined order, and at the page's end which of them make the
    # page: production has ~23 measurements a second, analysis here ~16 rows
    # a second. Compare only what the ORDER BY defines: the rows in order of
    # time, tied rows as a set, without the last time's (cut) group.
    rows = body["results"]
    assert all("measurement_start_time" in r for r in rows), "expected rows ordered by measurement_start_time"
    groups = {}
    for r in rows:
        groups.setdefault(r["measurement_start_time"], []).append(r)
    times = list(groups)[:-1]
    return {**body, "results": [sorted(groups[t], key=lambda r: json.dumps(r, sort_keys=True)) for t in times]}


# endpoints whose responses are partly approximate or undefined: compare
# the part that is defined
HASHED = {
    "private.circumvention_runtime_stats": _counts_only,
    **{name: _defined_order for name, (path, _) in CASES.items()
       if path in ("/api/v1/measurements", "/api/v1/observations", "/api/v1/analysis") and name not in EMPTY},
}


@pytest.mark.parametrize("name", CASES)
def test_bench_query(bench, bench_client, samples, name):
    path, params = CASES[name]
    params = {k: v.format(**samples) if isinstance(v, str) else v for k, v in params.items()}
    body = bench.query(bench_client, name, path, params, unordered=name in UNORDERED, hashed=HASHED.get(name))
    if name in EMPTY:
        assert not _has_data(body), f"{name} should find nothing: {body}"
    else:
        assert _has_data(body), f"{name} returned no data, the benchmark would be meaningless: {body}"
