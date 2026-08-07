"""Tests for the interval sampler's frame arithmetic.

No database. What is guarded here is the part that cannot be checked by looking
at the output: whether the strata cover the frame exactly once. A partition
that overlaps or leaks does not fail, it returns a plausible false-alarm rate
computed against the wrong denominator.
"""

from datetime import datetime

import pytest
from fastapi import HTTPException

from oonimeasurements.routers.labeling import (
    DEFAULT_VOLUME_FLOOR,
    INTERVAL_STRATA,
    VOLUME_BAND_EDGES,
    _design_fingerprint,
    _resolve_interval_predicates,
    _week_frame,
    volume_band,
)

ALL_STRATA = sorted(INTERVAL_STRATA)


def evaluate(predicate, alerted, blocked_max):
    """Evaluate a generated SQL predicate as Python.

    The alerted subquery is opaque to this, so it is substituted for a boolean:
    what is under test is how the strata compose, not how the join runs.
    """
    expr = predicate.replace(INTERVAL_STRATA["detector_alerted"]["predicate"], "alerted")
    expr = expr.replace(" AND ", " and ").replace("NOT ", "not ")
    if expr == "1":
        return True
    return eval(expr, {}, {"alerted": alerted, "blocked_max": blocked_max})


GRID = [(a, b) for a in (True, False) for b in (0.0, 0.49, 0.5, 1.0)]


@pytest.mark.parametrize(
    "wanted",
    [
        ["detector_alerted", "random_covered"],
        ["detector_alerted", "near_miss", "random_covered"],
        ["near_miss", "random_covered"],
        ["random_covered"],
    ],
)
def test_selected_strata_partition_the_frame(wanted):
    """Every cell-week in the frame lands in exactly one selected stratum.

    Two would give it two selection probabilities and no correct weight; none
    would drop it from the denominator silently, which biases the rate in the
    unsafe direction.
    """
    resolved = _resolve_interval_predicates(wanted)
    for alerted, blocked_max in GRID:
        hits = [s for s in wanted if evaluate(resolved[s], alerted, blocked_max)]
        assert len(hits) == 1, (alerted, blocked_max, hits)


def test_near_miss_alone_does_not_claim_the_frame():
    """Drawing only the importance stratum is allowed and estimates nothing on
    its own. It must not quietly widen to cover cells it did not screen for."""
    resolved = _resolve_interval_predicates(["near_miss"])
    assert not evaluate(resolved["near_miss"], False, 0.0)
    assert not evaluate(resolved["near_miss"], True, 1.0)


def test_alerted_and_near_miss_are_disjoint():
    resolved = _resolve_interval_predicates(["detector_alerted", "near_miss"])
    for alerted, blocked_max in GRID:
        hits = [s for s in resolved if evaluate(resolved[s], alerted, blocked_max)]
        assert len(hits) <= 1, (alerted, blocked_max, hits)


def test_volume_bands_are_ordered_and_total():
    assert volume_band(0) == "low"
    assert volume_band(DEFAULT_VOLUME_FLOOR) == "low"
    assert volume_band(99) == "low"
    assert volume_band(100) == "medium"
    assert volume_band(999) == "medium"
    assert volume_band(1000) == "high"
    assert volume_band(10**9) == "high"
    # Monotone, so a busier cell-week never lands in a quieter band.
    seen = [volume_band(n) for n in (1, 100, 1000)]
    assert seen == [name for _, name in VOLUME_BAND_EDGES]


def test_frame_snaps_to_whole_weeks():
    # A Thursday to a Thursday: both ends move to the Mondays inside the range.
    lo, hi = _week_frame(datetime(2026, 3, 5), datetime(2026, 4, 2))
    assert lo == datetime(2026, 3, 9)
    assert hi == datetime(2026, 3, 30)
    assert lo.weekday() == 0 and hi.weekday() == 0
    assert (hi - lo).days % 7 == 0


def test_frame_already_aligned_is_left_alone():
    lo, hi = _week_frame(datetime(2026, 3, 9), datetime(2026, 3, 30))
    assert (lo, hi) == (datetime(2026, 3, 9), datetime(2026, 3, 30))


def test_frame_without_a_whole_week_is_rejected():
    """Rather than returning a shorter observation window as if it were a
    smaller one."""
    with pytest.raises(HTTPException):
        _week_frame(datetime(2026, 3, 10), datetime(2026, 3, 14))


def test_design_id_tracks_the_partition():
    """The resolved predicate is in the spec, so the same nominal stratum drawn
    under a different partition gets a different id — a weight can never be
    reinterpreted under rules it was not drawn under."""
    two = _resolve_interval_predicates(["detector_alerted", "random_covered"])
    three = _resolve_interval_predicates(
        ["detector_alerted", "near_miss", "random_covered"]
    )
    assert two["random_covered"] != three["random_covered"]
    assert _design_fingerprint({"strata": two}) != _design_fingerprint({"strata": three})
