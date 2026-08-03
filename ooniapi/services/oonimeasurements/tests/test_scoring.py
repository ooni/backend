"""Tests for the single place a score becomes a verdict.

These are cheap and there is no database, but they guard the thing that went
wrong before centralising: two call sites drifting to different comparisons.
"""

import itertools

import pytest

from oonimeasurements import scoring
from oonimeasurements.routers.data import aggregate_analysis
from oonimeasurements.routers.labeling import STRATA


def evaluate(predicate, dns, tcp, tls):
    """Evaluate a generated SQL predicate as Python. The two agree on the
    operators used here (>=, <, AND -> and, greatest -> max)."""
    expr = predicate.replace(" AND ", " and ").replace("greatest(", "max(")
    return eval(expr, {"max": max},
                {"dns_blocked": dns, "tcp_blocked": tcp, "tls_blocked": tls})


GRID = [0.0, 0.2, 0.49, 0.5, 0.51, 0.8, 1.0]
POINTS = list(itertools.product(GRID, repeat=3))


def test_layer_attributions_are_mutually_exclusive():
    """A measurement must land in exactly one layer stratum, or the populations
    overlap and every sampling weight built from them is wrong."""
    for point in POINTS:
        hits = [l for l in scoring.LAYERS
                if evaluate(scoring.attributed_to(l), *point)]
        assert len(hits) <= 1, (point, hits)


def test_attributions_partition_exactly_what_any_blocked_selects():
    for point in POINTS:
        hits = [l for l in scoring.LAYERS
                if evaluate(scoring.attributed_to(l), *point)]
        assert bool(hits) == evaluate(scoring.any_blocked(), *point), point


def test_boundary_is_inclusive():
    """dns.failure_no_ctrl scores exactly 0.5. Whether that counts as blocked
    was the disagreement between the two call sites; it counts."""
    assert evaluate(scoring.layer_blocked("dns"), 0.5, 0, 0)
    assert evaluate(scoring.any_blocked(), 0.5, 0, 0)
    assert not evaluate(scoring.layer_not_blocked("dns"), 0.5, 0, 0)


def test_aggregation_and_sampling_use_the_same_comparison():
    """The regression this module exists to prevent: the aggregation router
    said `> 0.5` while the sampling strata said `>= 0.5`."""
    sql = aggregate_analysis.format_aggregate_query({"domain": "domain"}, "WHERE 1")
    assert f"x.1 >= {scoring.BLOCKING_THRESHOLD}" in sql
    assert "x.1 > 0.5," not in sql
    for layer in scoring.LAYERS:
        assert STRATA[f"screen_{layer}"]["predicate"] == scoring.attributed_to(layer)


def test_threshold_flows_into_generated_predicates():
    for t in (0.3, 0.7):
        assert scoring.layer_blocked("dns", t) == f"dns_blocked >= {t}"
        assert f">= {t}" in scoring.any_blocked(t)
        assert scoring.attributed_to("tls", t).count(str(t)) == 3


@pytest.mark.parametrize("bad", ["http", "", "DNS"])
def test_unknown_layers_are_rejected(bad):
    for fn in (scoring.layer_blocked, scoring.layer_not_blocked,
               scoring.attributed_to):
        with pytest.raises(ValueError):
            fn(bad)
