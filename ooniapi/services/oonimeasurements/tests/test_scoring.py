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


# ------------------------------------------------------------- calibration

def test_probability_is_monotone_and_bounded():
    ps = [scoring.blocked_probability(s) for s in
          [i / 100 for i in range(0, 101)]]
    assert all(0.0 < p < 1.0 for p in ps)
    assert all(a < b for a, b in zip(ps, ps[1:]))


def test_threshold_sits_near_even_odds():
    """The fitted calibration puts the deployed threshold at roughly a 50%
    posterior, which is why publishing probabilities moves no decisions. If a
    refit breaks this the two knobs have drifted apart and one of them needs
    revisiting -- deliberately, not by surprise."""
    p = scoring.blocked_probability(scoring.BLOCKING_THRESHOLD)
    assert 0.4 < p < 0.6, p


def test_sql_and_python_agree():
    """The API computes this in ClickHouse and the notebook in Python. They
    are two implementations of one formula and must not drift."""
    sql = scoring.blocked_probability_sql("SCORE")
    for s in (0.0, 0.2, 0.5, 0.75, 1.0):
        # ClickHouse pow(a,b) and Python a**b agree on these operands.
        expr = sql.replace("SCORE", repr(s)).replace("pow(", "__pow(")
        got = eval(expr, {"__pow": lambda a, b: a ** b}, {})
        assert abs(got - scoring.blocked_probability(s)) < 1e-12, s


def test_sql_does_not_overflow_at_the_extremes():
    """`pow(10,x)/(1+pow(10,x))` returns nan for large x; the reciprocal form
    used here does not. Worth pinning: it fails only on the rows that matter."""
    def ch_pow(a, b):
        # ClickHouse evaluates in float64: overflow saturates to inf rather
        # than raising, which is what makes the reciprocal form safe.
        try:
            return float(a) ** float(b)
        except OverflowError:
            return float("inf")

    sql = scoring.blocked_probability_sql("SCORE")
    for s in (-50.0, 50.0, 1e6, -1e6):
        expr = sql.replace("SCORE", repr(s)).replace("pow(", "__pow(")
        p = eval(expr, {"__pow": ch_pow}, {})
        assert 0.0 <= p <= 1.0 and p == p, (s, p)


def test_calibration_carries_its_own_uncertainty():
    """A published probability without the fit behind it is a number with no
    provenance. These are what the response advertises."""
    lo, hi = scoring.Calibration.INTERCEPT_CI
    assert lo < scoring.Calibration.INTERCEPT < hi
    lo, hi = scoring.Calibration.SLOPE_CI
    assert lo < scoring.Calibration.SLOPE < hi
    assert scoring.Calibration.CORPUS
    assert scoring.Calibration.RIDGE > 0, (
        "an unpenalised fit on this corpus is separable and the slope runs away")


def test_natural_log_sigmoid_would_be_wrong():
    """Guards the silent-failure mode: exp() on a log10 score agrees at 0 and
    stays in [0,1], so nothing else would catch it."""
    import math
    for s in (-1.0, 1.0):
        assert abs(scoring.log10_odds_to_prob(s) - 1 / (1 + math.exp(-s))) > 0.15
    assert scoring.log10_odds_to_prob(0.0) == pytest.approx(0.5)
