"""Where a continuous blocking score becomes a yes-or-no answer.

The pipeline writes `{dns,tcp,tls}_blocked` in [0, 1] and stops there. Turning
those into "this measurement is blocked" needs a threshold, and the threshold
is a *presentation* decision, not a pipeline one: changing it costs a deploy of
this service, no reprocessing, and never rewrites a stored row.

It lives here because it was previously written out three times — twice as
`>= 0.5` in the labeling router, once as `> 0.5` in the aggregation router. The
two disagreed at exactly 0.5, which is not hypothetical: `dns.failure_no_ctrl`
(DNS failing with no usable control) scores exactly 0.5 and is the sole rule
that does, so roughly 3% of flagged measurements were blocked to the labeller
and not blocked to the aggregation API.

The comparison is `>=`: a rule's weight is meant to be reachable, and the
labelling corpus was drawn under `>=`, so any calibration fitted on it
describes `>=` behaviour.

## Changing it

`analysis-evaluation.ipynb` in the pipeline repo simulates a change against
adjudicated labels before you make it: set `THRESHOLDS` there, read the
sensitivity/specificity/false-alarm columns, then edit `BLOCKING_THRESHOLD`
here and bump `SCORING_VERSION`. The notebook's numbers only describe this
service if the two agree, so treat a change here without a matching simulation
as unreviewed.

## What this is NOT

Not the rule weights. Those are `blocked`/`down`/`ok` in the pipeline's
`analysis/rules.py`, they are baked into stored rows, and changing one needs a
reprocess plus a `RULES_VERSION` bump. The threshold decides where the line
sits; the weights decide where each measurement sits relative to it.

Not the event detector. It consumes the continuous scores through
`quantile(0.5)` — a median over a cell, not a threshold — so nothing here
affects changepoints or alerts.
"""

from typing import List, Optional

# The line between blocked-leaning and not, applied to a `*_blocked` score.
BLOCKING_THRESHOLD = 0.5

# Identifies the (rule weights, threshold, calibration) triple a verdict was
# produced under. Bump on any change to BLOCKING_THRESHOLD or CALIBRATION, or
# when the pipeline's RULES_VERSION changes, so a stored or exported verdict
# can always name the scoring regime that produced it. Two verdicts with
# different values here are not comparable, however similar they look.
SCORING_VERSION = "2"

LAYERS = ("dns", "tcp", "tls")


# --------------------------------------------------------------------------
# Calibration: turning the score into a probability that means something
# --------------------------------------------------------------------------
#
# `greatest(dns_blocked, tcp_blocked, tls_blocked)` is a fuzzy-logic score built
# from hand-set constants. It ranks measurements sensibly but its magnitude is
# not a probability, and shipping it as though it were is the misreading
# ontology.md warns about.
#
# So map it through a fitted logistic:
#
#     log10-odds(blocked) = INTERCEPT + SLOPE * score
#     P(blocked)          = 1 / (1 + 10^-(log10-odds))
#
# Two properties this buys, neither of which the raw score has: the number is
# comparable across measurements and over time, and it is falsifiable — group
# everything reported at 0.9 and roughly 90% of it should be blocked.


class Calibration:
    """Logistic map from the fuzzy score to a population probability.

    Fitted in `docs/analysis-evaluation.ipynb` (pipeline repo) against the
    adjudicated corpus. Refit there and paste the result here; do not tune by
    hand, the whole point is that these are measured.
    """

    __slots__ = ()

    # log10-odds units. Fitted with SAMPLING WEIGHTS: the corpus oversamples
    # positives by design, so an unweighted fit describes the corpus rather
    # than the network and reports roughly 10x too much blocking.
    INTERCEPT = -2.3594
    SLOPE = 4.7413

    # 95% bootstrap intervals, 400 resamples within stratum.
    INTERCEPT_CI = (-2.563, -2.149)
    SLOPE_CI = (4.094, 5.688)

    # The classes are nearly separable at this corpus size, which sends an
    # unpenalised logistic slope to infinity — the unregularised fit had a
    # bootstrap CI on SLOPE of [4.7, 6521] and a leave-one-out log loss of 8.2
    # against 0.025 here. RIDGE is the L2 penalty on the slope that minimised
    # leave-one-out weighted log loss, so it is selected, not chosen.
    RIDGE = 0.0005
    LOO_LOG_LOSS = 0.02533

    CORPUS = "2026-08-03, 89 adjudicated labels (27 blocked)"

    # What the numbers can and cannot support. The middle of the curve is
    # constrained by data; the tails are extrapolation from a handful of
    # points, so 0.995 and 0.95 are not meaningfully different claims and
    # should not be presented as if they were.
    TRUSTWORTHY_RANGE = (0.05, 0.95)


def log10_odds_to_prob(log10_odds: float) -> float:
    """Inverse logit for log10-odds. NOT the natural-log sigmoid.

    Applying `1 / (1 + exp(-x))` to one of these fails silently: it agrees at
    0, stays inside [0, 1] everywhere, and is simply wrong in between (at
    log10-odds 1.0, 0.73 instead of 0.91). Every score in this module is
    log10; nothing here should ever reach `math.exp`.
    """
    return 1.0 / (1.0 + 10.0 ** (-log10_odds))


def blocked_probability(score: float) -> float:
    """P(blocked) for one measurement, from its fuzzy blocking score."""
    return log10_odds_to_prob(Calibration.INTERCEPT + Calibration.SLOPE * score)


def blocked_probability_sql(score_expr: Optional[str] = None) -> str:
    """The same map as ClickHouse SQL.

    Written as `1 / (1 + pow(10, -x))` rather than `pow(10,x)/(1+pow(10,x))`
    so it cannot overflow to nan at the top of the range.
    """
    score = score_expr or f"greatest({', '.join(f'{l}_blocked' for l in LAYERS)})"
    return (
        f"1 / (1 + pow(10, -({Calibration.INTERCEPT} + "
        f"{Calibration.SLOPE} * ({score}))))"
    )


def _resolve(threshold: Optional[float]) -> float:
    """Read the module global at call time, not at def time.

    A `threshold=BLOCKING_THRESHOLD` default would bind once at import and then
    ignore any later override, so a test or a config layer that sets the
    constant would silently keep generating the old predicate.
    """
    return BLOCKING_THRESHOLD if threshold is None else threshold


def layer_blocked(layer: str, threshold: Optional[float] = None) -> str:
    """SQL predicate for "this layer is blocked-leaning"."""
    if layer not in LAYERS:
        raise ValueError(f"unknown layer: {layer}")
    return f"{layer}_blocked >= {_resolve(threshold)}"


def layer_not_blocked(layer: str, threshold: Optional[float] = None) -> str:
    """Negation of layer_blocked, written out so the two cannot drift apart."""
    if layer not in LAYERS:
        raise ValueError(f"unknown layer: {layer}")
    return f"{layer}_blocked < {_resolve(threshold)}"


def any_blocked(threshold: Optional[float] = None) -> str:
    """SQL predicate for "some layer is blocked-leaning".

    `greatest` across layers is the existential question — is there any layer
    saying blocked — so it is the right aggregate here. It is not a severity
    score: a measurement blocked at one layer and fine at two others scores the
    same as one blocked at all three.
    """
    cols = ", ".join(f"{layer}_blocked" for layer in LAYERS)
    return f"greatest({cols}) >= {_resolve(threshold)}"


def attributed_to(layer: str, threshold: Optional[float] = None) -> str:
    """SQL predicate attributing a measurement to the first blocked layer.

    Layers gate each other: a DNS-blocked measurement's TCP and TLS results are
    downstream of an untrustworthy address, so they are not evidence about TCP
    or TLS. Attribution therefore requires every earlier layer to be quiet,
    which also makes these predicates mutually exclusive — a measurement lands
    in exactly one, so populations built from them do not overlap.
    """
    if layer not in LAYERS:
        raise ValueError(f"unknown layer: {layer}")
    earlier = LAYERS[: LAYERS.index(layer)]
    parts: List[str] = [layer_blocked(layer, threshold)]
    parts += [layer_not_blocked(e, threshold) for e in earlier]
    return " AND ".join(parts)
