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

# Identifies the (rule weights, threshold) pair a verdict was produced under.
# Bump on any change to BLOCKING_THRESHOLD, or when the pipeline's
# RULES_VERSION changes, so a stored or exported verdict can always name the
# scoring regime that produced it. Two verdicts with different values here are
# not comparable, however similar they look.
SCORING_VERSION = "1"

LAYERS = ("dns", "tcp", "tls")


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
