"""Sampling-design tests for the labeling router.

These need no database. They cover the properties that decide whether the
corpus can say anything about production at all: if a weight is wrong, or two
replicates overlap, every likelihood ratio fitted from these labels is wrong by
an amount nobody can measure after the fact.
"""

from datetime import datetime

import pytest

from oonimeasurements.routers.labeling import (
    STRATA,
    _quotas,
    _resolve_shares,
    draw_sample,
)

FRAME = dict(since=datetime(2025, 8, 1), until=datetime(2026, 7, 31))
SCOPE = dict(probe_cc=None, probe_asn=None, domain=None,
             test_name="web_connectivity")


class FakeDB:
    """Returns a fixed population and as many rows as the quota asks for.

    `populations` maps a substring of the stratum predicate to a row count;
    a population of 0 stands in for a stratum that draws nothing.
    """

    def __init__(self, populations):
        self.populations = populations
        self.calls = []

    def _match(self, sql):
        """Which stratum this query is for, and how big its population is.

        Strata are namespaced because in production they are disjoint by
        predicate: a measurement is anomaly='t' or anomaly='f', never both.
        """
        for needle, pop in self.populations.items():
            if needle in sql:
                return needle, pop
        return None, 0

    def execute(self, sql, params=None, with_column_types=False):
        self.calls.append((sql, params))
        key, pop = self._match(sql)
        if "count()" in sql:
            return [(pop,)]
        if pop == 0:
            return []
        tag = abs(hash(key)) % 1000
        n = min(params["limit"], max(0, pop - params["offset"]))
        return [
            (f"uid{tag}-{params['offset'] + i}", datetime(2026, 7, 30, 12),
             "IT", 1, 0, "example.com", "http://example.com/",
             "web_connectivity")
            for i in range(n)
        ]


def draw(db, **kw):
    args = dict(strata="screen_positive,screen_negative", replicate=1,
                limit=50, shares=None, **FRAME, **SCOPE)
    args.update(kw)
    return draw_sample(db=db, **args)


# --------------------------------------------------------------- composition

def test_quotas_sum_to_limit_and_never_starve_a_stratum():
    for names in (["screen_positive", "screen_negative"], sorted(STRATA)):
        for limit in (1, 4, 7, 50, 500):
            shares = _resolve_shares(sorted(names), None)
            q = _quotas(shares, limit)
            if limit >= len(names):
                assert sum(q.values()) == limit, (names, limit, q)
            # A stratum in the design but absent from the queue is
            # indistinguishable from one that was never requested.
            assert all(v >= 1 for v in q.values()), (names, limit, q)


def test_shares_normalise_over_selected_strata():
    """Dropping a stratum redistributes its share rather than shrinking the
    queue: the queue is always `limit` rows."""
    two = _resolve_shares(["screen_negative", "screen_positive"], None)
    assert sum(two.values()) == pytest.approx(1.0)
    four = _resolve_shares(sorted(STRATA), None)
    assert sum(four.values()) == pytest.approx(1.0)
    # screen_positive keeps the larger share in both
    assert two["screen_positive"] > two["screen_negative"]


def test_share_override_changes_composition():
    shares = _resolve_shares(["screen_negative", "screen_positive"],
                             "screen_negative=0.75")
    q = _quotas(shares, 40)
    assert q["screen_negative"] > q["screen_positive"]
    assert sum(q.values()) == 40


@pytest.mark.parametrize("bad", ["nope=0.5", "screen_positive=abc",
                                 "screen_positive=0", "screen_positive=2"])
def test_bad_share_overrides_are_rejected(bad):
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _resolve_shares(["screen_positive", "screen_negative"], bad)


# ------------------------------------------------------------------ weights

def test_weight_is_population_over_drawn_not_one_over_share():
    """The queue is cut to a quota, so what a row stands for is set by the
    draw, not by any declared rate."""
    db = FakeDB({"anomaly = 't'": 5_000_000, "confirmed = 'f'": 200_000_000})
    r = draw(db)
    by_stratum = {s: v for s, v in r.strata.items()}
    pos = by_stratum["screen_positive"]
    assert pos["sampling_weight"] == pytest.approx(
        pos["population_estimate"] / pos["drawn"])
    # and the oversampling of positives falls out of the two weights
    neg = by_stratum["screen_negative"]
    assert neg["sampling_weight"] > pos["sampling_weight"]
    for row in r.rows:
        assert row.sampling_weight == by_stratum[row.sampling_stratum][
            "sampling_weight"]


def test_empty_stratum_yields_no_weight_and_does_not_crash():
    """A narrow scope, or a replicate past the end, draws nothing. Dividing by
    that would be a crash; inventing a weight would be worse."""
    db = FakeDB({"anomaly = 't'": 1000, "confirmed = 'f'": 0})
    r = draw(db)
    assert r.strata["screen_negative"]["drawn"] == 0
    assert r.strata["screen_negative"]["sampling_weight"] is None
    assert all(row.sampling_stratum == "screen_positive" for row in r.rows)


def test_exhausted_stratum_is_flagged():
    db = FakeDB({"anomaly = 't'": 5, "confirmed = 'f'": 1_000_000})
    r = draw(db)
    assert r.strata["screen_positive"]["exhausted"] is True
    assert r.strata["screen_negative"]["exhausted"] is False


# --------------------------------------------------------------- replicates

def test_replicates_take_disjoint_slices_of_one_ordering():
    """The documented promise: replicate 2 does not repeat replicate 1. That
    holds only if the ordering is stable and the offset walks it."""
    seen_uids, salts, design_ids = [], [], []
    for rep in (1, 2, 3):
        db = FakeDB({"anomaly = 't'": 1_000_000, "confirmed = 'f'": 1_000_000})
        r = draw(db, replicate=rep)
        seen_uids.append({row.measurement_uid for row in r.rows})
        salts.append([p["salt"] for _, p in db.calls if p and "salt" in p][0])
        design_ids.append(r.design_id)

    assert salts[0] == salts[1] == salts[2], "ordering must not reshuffle"
    assert len(set(design_ids)) == 3, "each replicate is its own design"
    assert not seen_uids[0] & seen_uids[1]
    assert not seen_uids[1] & seen_uids[2]


def test_population_scope_changes_the_ordering_salt():
    a = FakeDB({"anomaly = 't'": 1000, "confirmed = 'f'": 1000})
    draw(a)
    b = FakeDB({"anomaly = 't'": 1000, "confirmed = 'f'": 1000})
    draw(b, probe_cc="IT")
    salt = lambda db: [p["salt"] for _, p in db.calls if p and "salt" in p][0]
    assert salt(a) != salt(b)


# ------------------------------------------------------------------ the SQL

def test_selection_sql_has_no_redundant_hash_filter():
    """ORDER BY hash + LIMIT is already a uniform sample; a modulo prefilter
    selected a random subset of a random subset and controlled nothing."""
    db = FakeDB({"anomaly = 't'": 1000, "confirmed = 'f'": 1000})
    draw(db)
    sel = [q for q, _ in db.calls if "ORDER BY" in q][0]
    assert "modulo" not in sel
    assert "cityHash64(concat(measurement_uid, %(salt)s))" in sel
    assert "LIMIT %(limit)s OFFSET %(offset)s" in sel


def test_draw_is_restricted_to_labelable_rows():
    """The screens read fastpath but /candidate reads obs_web, so an
    unrestricted draw yields rows that 404 on open, and the dropouts are not
    random."""
    db = FakeDB({"anomaly = 't'": 1000, "confirmed = 'f'": 1000})
    draw(db)
    for sql, _ in db.calls:
        assert "SELECT measurement_uid FROM obs_web" in sql, (
            "both the count and the draw must use the same eligible set, or "
            "population/drawn stops being an inclusion probability")


def test_no_pipeline_verdict_columns_reach_the_draw():
    db = FakeDB({"anomaly = 't'": 1000, "confirmed = 'f'": 1000})
    draw(db)
    sel = [q for q, _ in db.calls if "ORDER BY" in q][0]
    projection = sel.split("FROM")[0]
    for leaked in ("blocked", "anomaly", "confirmed", "scores",
                   "probe_analysis"):
        assert leaked not in projection
