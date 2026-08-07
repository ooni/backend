"""
Labeling corpus API.

Read-only ClickHouse queries backing the adjudication UIs. There is no write
path: labels live in the analyst's browser and leave it by copy-paste, so this
router adds no storage, no auth surface, and no migration.

Two grains are served, and they answer different questions.

- MEASUREMENT (/sample, /candidate, /context, /reveal). One row per
  measurement. Calibrates *scoring*: the per-rule likelihood ratios are fitted
  from it.
- INTERVAL (/interval_sample, /interval_reveal). One row per
  (probe_cc, probe_asn, domain) x ISO week — the detector's own cell, keyed
  exactly as `event_detector_cusums` is. Supplies the *denominator* the event
  grain cannot: "false alerts per silent series-week" is a rate over a
  population of cell-weeks, and a population can only be counted if it was
  sampled from a frame. Silent, not quiet: a week inside an ongoing block also
  contains no transition for a changepoint detector to find, so it belongs in
  the denominator too.

Two invariants this module exists to enforce, in both grains:

1. BLINDING. The candidate views return what the probes got and nothing the
   pipeline concluded. analysis_web_measurement and fastpath's anomaly /
   confirmed / scores columns are queried ONLY by /reveal, and
   event_detector_changepoints ONLY by /interval_reveal, which the UIs call
   after the analyst has committed. If you add a field to a candidate view,
   check it is not a pipeline judgment in disguise. The interval grain makes
   this sharper than the measurement grain does: one of its strata *is* the
   detector's output, so an unblinded alert state does not merely anchor the
   analyst, it hands them the answer.

2. SAMPLING IS RECORDED, NOT REMEMBERED. Every draw is deterministic given
   (design_id, stratum, frame, rate), and the sample endpoints return the
   predicate they ran and the population they ran against, so the weights are
   reconstructable from the export alone.
"""

import time
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

# ooni/backend wires this up already; the import path is the one used by the
# existing data routers.
from ..dependencies import get_clickhouse_session  # type: ignore
from ..scoring import BLOCKING_THRESHOLD, SCORING_VERSION, any_blocked, attributed_to

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/labeling", tags=["labeling"])


# --------------------------------------------------------------------------
# Sampling design
# --------------------------------------------------------------------------
#
# The design doc's screen is "any blocked-leaning RULE fired", which needs B1
# (persisted fired-rule sets) to exist. It does not yet, so the screen below is
# a documented PROXY over the fastpath analysis which is derived from probe
# computed values. It's fine to use this as a PROXY, as it's recorded in the
# measurement itself and is stable, since we have not plans to change the
# fastpath scoring logic.
#
# This matters for the weights: the proxy screen has different, unmeasured
# coverage from the real one. Record `screen_kind` in the export so a later
# refit can tell proxy-screened rows from B1-screened ones and, if needed,
# drop the former.


STRATA: Dict[str, Dict[str, Any]] = {
    "screen_positive": {
        "table": "fastpath",
        # confirmed rows are excluded: they are certain blocking with a known
        # artefact, so a label on one adds almost nothing, and they were eating
        # the positive quota. They keep their own census stratum below.
        "predicate": f"anomaly = 't' AND confirmed = 'f' AND msm_failure = 'f'",
        "screen_kind": "fastpath_proxy",
        "note": "Proxy for B1's blocked-leaning-rule screen. LR numerator.",
    },
    # Layer-attributed positives. A uniform draw from anomaly='t' oversamples
    # whichever mechanism dominates globally (in practice TLS resets), so a
    # corpus built from it calibrates one layer and starves the others. These
    # read the pipeline's own layer scores, which means they oversample what
    # the pipeline can already see — screen_negative stays the only stratum
    # that can discover what it misses. Predicates are mutually exclusive so
    # populations do not overlap and weights stay clean.
    "screen_dns": {
        "table": "analysis_web_measurement",
        "predicate": attributed_to("dns"),
        "screen_kind": "loni_layer_proxy",
        "note": "DNS-attributed positives.",
    },
    "screen_tcp": {
        "table": "analysis_web_measurement",
        "predicate": attributed_to("tcp"),
        "screen_kind": "loni_layer_proxy",
        "note": "TCP-attributed positives, DNS quiet.",
    },
    "screen_tls": {
        "table": "analysis_web_measurement",
        "predicate": attributed_to("tls"),
        "screen_kind": "loni_layer_proxy",
        "note": "TLS-attributed positives, DNS and TCP quiet.",
    },
    "screen_negative": {
        "table": "fastpath",
        "predicate": f"confirmed = 'f' AND anomaly = 'f' AND msm_failure = 'f'",
        "screen_kind": "fastpath_proxy",
        "note": "Bounds false negatives and carries the base rate. Small, "
                "and the first thing cut under pressure. Do not cut it.",
    },
    "fingerprint_match": {
        "table": "fastpath",
        "predicate": "confirmed = 't' AND msm_failure = 'f'",
        "screen_kind": "fingerprint",
        "note": "Census, not a sample. High-precision positives; tag the "
                "labels so LRs can be refit without them as a circularity "
                "check.",
    },
    "incident_window": {
        "table": "analysis_web_measurement",
        "predicate": "1",  # scoped entirely by the cc/domain/time params
        "screen_kind": "incident_scope",
        "note": "Draw inside a known event. Label the MEASUREMENT: rows here "
                "that are genuinely ok are the most valuable in the corpus.",
    },
}

# control_agreement (cheap negatives from probe/control agreement) needs an
# obs_web_ctrl join with per-layer agreement predicates. Left out on purpose
# rather than half-built: a negative stratum with a wrong predicate is worse
# than one that is absent, because it silently deflates every LR denominator.

# Bump when STRATA definitions or the fingerprint's shape change: it forces new
# design ids, so old weights are never silently reinterpreted under new rules.
DESIGN_SCHEMA_VERSION = "2"


def _quotas(wanted: List[str], shares: Optional[str], limit: int) -> Dict[str, int]:
    """How many rows each stratum contributes to the queue.

    Default is an equal split. `shares` reweights it — "screen_negative=0.5"
    gives that stratum half the queue and splits the rest equally. Shares only
    steer analyst effort; the weights on the rows are population/drawn either
    way, so no share choice can bias an estimate, only its variance.
    """
    fractions = {s: 1.0 for s in wanted}
    if shares:
        for part in shares.split(","):
            name, _, value = part.partition("=")
            name = name.strip()
            if name not in wanted:
                raise HTTPException(400, f"share for unknown stratum: {name}")
            try:
                fractions[name] = float(value)
            except ValueError:
                raise HTTPException(400, f"bad share: {part}")
            if fractions[name] <= 0:
                raise HTTPException(400, f"share must be positive: {part}")
    total = sum(fractions.values())
    exact = {s: limit * f / total for s, f in fractions.items()}
    quotas = {s: max(1, int(e)) for s, e in exact.items()}
    # Hand out what rounding left over, largest remainder first.
    leftover = limit - sum(quotas.values())
    for s in sorted(exact, key=lambda s: exact[s] - int(exact[s]), reverse=True):
        if leftover <= 0:
            break
        quotas[s] += 1
        leftover -= 1
    # The min-1 floors can overshoot under an extreme share; trim the largest
    # quotas back so the recorded drawn counts always match the returned queue.
    while sum(quotas.values()) > limit:
        biggest = max(quotas, key=lambda s: quotas[s])
        if quotas[biggest] == 1:
            break  # limit < number of strata; nothing sensible to trim
        quotas[biggest] -= 1
    return quotas


def _design_fingerprint(spec: Dict[str, Any]) -> str:
    """Content-address a sampling design.

    The id is derived from the design so that there is never the same id used
    for two different parameter sets, leaving two incompatible weightings
    sharing a name.

    Redrawing with a higher limit returns a superset of the same rows, and two
    analysts who enter the same parameters get the same queue, which is how
    inter-rater agreement gets measured without any coordination service.

    Want genuinely fresh rows from the same population? Increment `replicate`.
    It is part of the spec, so it produces a different id and an independent
    draw, on purpose and on the record.
    """
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":"), default=str)
    return "d" + hashlib.sha256(blob.encode()).hexdigest()[:10]


class SampleRow(BaseModel):
    measurement_uid: str
    measurement_start_time: datetime
    probe_cc: str
    probe_asn: int
    resolver_asn: int
    domain: str
    input: Optional[str]
    test_name: str
    # sampling provenance, carried through to the label
    sampling_stratum: str
    sampling_weight: float
    sample_population: int
    sample_rows: int
    sampling_design_id: str
    screen_kind: str


class SampleResponse(BaseModel):
    design_id: str
    replicate: int
    spec: Dict[str, Any]
    frame_start: datetime
    frame_end: datetime
    strata: Dict[str, Dict[str, Any]]
    rows: List[SampleRow]


def _frame(since: Optional[datetime], until: Optional[datetime]):
    until = until or datetime.now(timezone.utc).replace(tzinfo=None)
    since = since or (until - timedelta(days=30))
    if since >= until:
        raise HTTPException(400, "since must be before until")
    return since, until


@router.get("/test_names")
def list_test_names(
    db=Depends(get_clickhouse_session),
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    probe_cc: Optional[str] = Query(None, min_length=2, max_length=2),
) -> Dict[str, Any]:
    """What is labelable in this frame, and how much of it there is.

    Counted from analysis_web_measurement rather than fastpath on purpose: a
    test with fastpath rows but no analysis rows will draw fine and then fail
    to load, because the candidate view reads obs_web. This list is the set
    that actually works end to end.
    """
    since_dt, until_dt = _frame(since, until)
    where = [
        "measurement_start_time >= %(since)s",
        "measurement_start_time < %(until)s",
    ]
    params: Dict[str, Any] = {"since": since_dt, "until": until_dt}
    if probe_cc:
        where.append("probe_cc = %(probe_cc)s")
        params["probe_cc"] = probe_cc.upper()

    rows = db.execute(
        f"""
        SELECT test_name,
               count() AS n,
               countIf({any_blocked()})
                   AS n_screen_positive
        FROM analysis_web_measurement
        WHERE {' AND '.join(where)}
        GROUP BY test_name
        ORDER BY n DESC
        """,
        params,
    )
    return {
        "frame_start": since_dt,
        "frame_end": until_dt,
        "test_names": [
            {
                "test_name": r[0],
                "measurements": int(r[1]),
                "screen_positive": int(r[2]),
            }
            for r in rows
        ],
    }


@router.get("/sample", response_model=SampleResponse)
def draw_sample(
    db=Depends(get_clickhouse_session),
    strata: str = Query(
        "screen_positive,screen_negative",
        description="Comma-separated. Multiple strata are drawn separately "
                    "and interleaved, so the analyst cannot infer a row's "
                    "stratum from its position in the queue.",
    ),
    replicate: int = Query(
        1, ge=1,
        description="Independent draws of the same design. Same replicate = "
                    "same rows (reproducible, extendable, comparable across "
                    "analysts). Increment it to sample rows the previous "
                    "replicate did not cover.",
    ),
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    probe_cc: Optional[str] = Query(None, min_length=2, max_length=2),
    probe_asn: Optional[int] = None,
    domain: Optional[str] = None,
    test_name: Optional[str] = Query(
        "web_connectivity",
        description="Comma-separated. Scoping a design to a test changes its "
                    "population, so weights are only valid within the same "
                    "test scope — change design_id when you change this. "
                    "Empty string means every test.",
    ),
    shares: Optional[str] = Query(
        None,
        description="Optional stratum=share pairs, e.g. "
                    "'screen_negative=0.5'. Reweights how the queue is split "
                    "across the selected strata; omitted strata share the "
                    "remainder equally. Steers effort only — row weights stay "
                    "population/drawn regardless.",
    ),
    limit: int = Query(50, ge=1, le=500),
) -> SampleResponse:
    since_dt, until_dt = _frame(since, until)
    wanted = sorted({s.strip() for s in strata.split(",") if s.strip()})
    unknown = [s for s in wanted if s not in STRATA]
    if unknown:
        raise HTTPException(400, f"unknown strata: {unknown}")

    tests = sorted({t.strip() for t in (test_name or "").split(",") if t.strip()})
    if "incident_window" in wanted and not (probe_cc and domain):
        raise HTTPException(
            400,
            "incident_window needs probe_cc and domain — an unscoped incident "
            "draw is just a biased production sample",
        )

    # The spec is the design. Everything that changes which rows are eligible,
    # or what a weight means, has to be in here — otherwise two different
    # populations could collide onto one id, which is the failure this exists
    # to make impossible.
    resolved = {
        s: {
            "table": STRATA[s]["table"],
            "predicate": STRATA[s]["predicate"],
            "screen_kind": STRATA[s]["screen_kind"],
        }
        for s in wanted
    }
    spec = {
        "schema": DESIGN_SCHEMA_VERSION,
        # The layer strata are defined by BLOCKING_THRESHOLD, so a threshold
        # change redefines what "DNS-blocked" means and the labels drawn either
        # side are not one population. The predicates below already carry the
        # number, but recording the version states it, and keeps the id
        # sensitive to a scoring change that happens to render identically.
        "scoring_version": SCORING_VERSION,
        "blocking_threshold": BLOCKING_THRESHOLD,
        "strata": resolved,
        "frame": [since_dt.isoformat(), until_dt.isoformat()],
        "scope": {
            "probe_cc": probe_cc.upper() if probe_cc else None,
            "probe_asn": probe_asn,
            "domain": domain,
            "test_names": tests or "all",
        },
        "replicate": replicate,
    }
    derived_id = _design_fingerprint(spec)

    # Shares, like limit, set how far down each stratum's fixed ordering the
    # draw goes. They are deliberately not part of the spec: the same design
    # with a bigger share returns a superset of the same stratum rows.
    quotas = _quotas(wanted, shares, limit)
    used: Dict[str, Dict[str, Any]] = {}
    buckets: List[List[SampleRow]] = []

    for stratum in wanted:
        spec_s = STRATA[stratum]
        table = spec_s["table"]
        # analysis_web_measurement is a ReplacingMergeTree; during a reprocess
        # the same uid exists in old and new versions until the merge runs,
        # which would inflate the population and can draw a uid twice.
        from_clause = f"{table} FINAL" if table == "analysis_web_measurement" else table

        where = [
            "measurement_start_time >= %(since)s",
            "measurement_start_time < %(until)s",
            f"({spec_s['predicate']})",
        ]
        params: Dict[str, Any] = {
            "since": since_dt,
            "until": until_dt,
            "salt": f"{derived_id}:{stratum}",
            "limit": quotas[stratum],
        }
        if probe_cc:
            where.append("probe_cc = %(probe_cc)s")
            params["probe_cc"] = probe_cc.upper()
        if probe_asn:
            where.append("probe_asn = %(probe_asn)s")
            params["probe_asn"] = probe_asn
        if domain:
            where.append("domain = %(domain)s")
            params["domain"] = domain
        if tests:
            where.append("test_name IN %(test_names)s")
            params["test_names"] = tests
        where_sql = " AND ".join(where)

        # Population first: the weight is 1/rate by construction, but the
        # population is what lets anyone check that later.
        pop = db.execute(
            f"SELECT count() FROM {from_clause} WHERE {where_sql}", params
        )
        population = int(pop[0][0]) if pop else 0

        resolver = (
            "resolver_asn" if table == "analysis_web_measurement" else "0"
        )
        # NOTE: no blocked/down/ok, no anomaly, no confirmed, no scores.
        rows = db.execute(
            f"""
            SELECT measurement_uid,
                   measurement_start_time,
                   probe_cc,
                   probe_asn,
                   {resolver} AS resolver_asn,
                   domain,
                   input,
                   test_name
            FROM {from_clause}
            WHERE {where_sql}
            ORDER BY cityHash64(concat(measurement_uid, %(salt)s))
            LIMIT %(limit)s
            """,
            params,
        )

        used[stratum] = {
            "predicate": spec_s["predicate"],
            "table": table,
            "screen_kind": spec_s["screen_kind"],
            "population_estimate": population,
            "drawn": len(rows),
            "frame_start": since_dt.isoformat(),
            "frame_end": until_dt.isoformat(),
            "scope": spec["scope"],
        }
        buckets.append([
            SampleRow(
                measurement_uid=r[0],
                measurement_start_time=r[1],
                probe_cc=r[2] or "",
                probe_asn=int(r[3] or 0),
                resolver_asn=int(r[4] or 0),
                domain=r[5] or "",
                input=r[6],
                test_name=r[7] or "",
                sampling_stratum=stratum,
                sampling_weight=population / len(rows),
                sample_population=population,
                sample_rows=len(rows),
                sampling_design_id=derived_id,
                screen_kind=spec_s["screen_kind"],
            )
            for r in rows
        ])

    # Interleave rather than concatenate. A queue that runs all the positives
    # first tells the analyst which stratum they are in, which is most of the
    # way to telling them the answer.
    interleaved: List[SampleRow] = []
    for i in range(max((len(b) for b in buckets), default=0)):
        for b in buckets:
            if i < len(b):
                interleaved.append(b[i])

    return SampleResponse(
        design_id=derived_id,
        replicate=replicate,
        spec=spec,
        frame_start=since_dt,
        frame_end=until_dt,
        strata=used,
        rows=interleaved[:limit],
    )


# --------------------------------------------------------------------------
# The blinded candidate
# --------------------------------------------------------------------------


def _rows_to_dicts(result, columns) -> List[Dict[str, Any]]:
    return [dict(zip(columns, row)) for row in result]


@router.get("/candidate/{measurement_uid}")
def get_candidate(
    measurement_uid: str,
    db=Depends(get_clickhouse_session),
) -> Dict[str, Any]:
    """Everything needed to judge one measurement, and nothing more.

    Deliberately absent: the LoNI triple, top_probe_analysis, anomaly,
    confirmed, scores. Those are what the corpus exists to evaluate; an
    analyst who sees them first is anchored, and every LR fit from those
    labels is inflated by an amount nobody can measure. See /reveal.
    """
    obs = db.execute(
        """
        SELECT * FROM obs_web
        WHERE measurement_uid = %(uid)s
        ORDER BY observation_idx
        """,
        {"uid": measurement_uid},
        with_column_types=True,
    )
    obs_rows, obs_types = obs
    obs_cols = [c[0] for c in obs_types]
    if not obs_rows:
        raise HTTPException(404, "no observations for that measurement_uid")

    # obs_web_ctrl's exact columns vary by pipeline version, so select * and
    # let the client field-match. Verify against your deployment before
    # trusting the diff.
    ctrl_rows, ctrl_types = db.execute(
        "SELECT * FROM obs_web_ctrl WHERE measurement_uid = %(uid)s",
        {"uid": measurement_uid},
        with_column_types=True,
    )
    ctrl_cols = [c[0] for c in ctrl_types]

    return {
        "measurement_uid": measurement_uid,
        "observations": _rows_to_dicts(obs_rows, obs_cols),
        "controls": _rows_to_dicts(ctrl_rows, ctrl_cols),
        "blinded": True,
    }


@router.get("/context")
def get_context(
    hostname: str,
    probe_cc: str = Query(..., min_length=2, max_length=2),
    probe_asn: int = Query(...),
    at: datetime = Query(..., description="Centre of the window"),
    hours: int = Query(6, ge=1, le=72),
    db=Depends(get_clickhouse_session),
) -> Dict[str, Any]:
    """Failure-string counts per hour for this hostname on this network,
    centred on the measurement.

    This is the panel that separates "one probe had a bad minute" from "this
    network stopped resolving this name at 14:00". It is failure strings only —
    still no verdicts.
    """
    rows = db.execute(
        """
        WITH multiIf(
            dns_failure IS NOT NULL, concat('dns.', dns_failure),
            tcp_failure IS NOT NULL, concat('tcp.', tcp_failure),
            tls_failure IS NOT NULL, concat('tls.', tls_failure),
            http_failure IS NOT NULL, concat('http.', http_failure),
            'ok'
        ) AS failure_str
        SELECT toStartOfHour(measurement_start_time) AS ts,
               failure_str,
               resolver_asn,
               count() AS cnt
        FROM obs_web
        WHERE hostname = %(hostname)s
          AND probe_cc = %(cc)s
          AND probe_asn = %(asn)s
          AND measurement_start_time >= %(since)s
          AND measurement_start_time < %(until)s
        GROUP BY ts, failure_str, resolver_asn
        ORDER BY ts
        """,
        {
            "hostname": hostname,
            "cc": probe_cc.upper(),
            "asn": probe_asn,
            "since": at - timedelta(hours=hours),
            "until": at + timedelta(hours=hours),
        },
    )
    return {
        "hostname": hostname,
        "window_hours": hours,
        "series": [
            {
                "ts": r[0],
                "failure_str": r[1],
                "resolver_asn": int(r[2] or 0),
                "count": int(r[3]),
            }
            for r in rows
        ],
    }


# --------------------------------------------------------------------------
# The reveal — called only after the analyst commits
# --------------------------------------------------------------------------


@router.get("/reveal/{measurement_uid}")
def reveal(
    measurement_uid: str,
    db=Depends(get_clickhouse_session),
) -> Dict[str, Any]:
    """What the pipeline concluded.

    Shown after commit, never before. Two uses: analysts find rule bugs this
    way, and the agreement rate between analyst and pipeline is a diagnostic
    worth watching — as a signal that blinding is holding, not as a target to
    improve.
    """
    a = db.execute(
        """
        SELECT top_probe_analysis, top_dns_failure, top_tcp_failure,
               top_tls_failure,
               dns_blocked, dns_down, dns_ok,
               tcp_blocked, tcp_down, tcp_ok,
               tls_blocked, tls_down, tls_ok
        FROM analysis_web_measurement
        WHERE measurement_uid = %(uid)s
        LIMIT 1
        """,
        {"uid": measurement_uid},
    )
    f = db.execute(
        """
        SELECT anomaly, confirmed, msm_failure, scores
        FROM fastpath WHERE measurement_uid = %(uid)s LIMIT 1
        """,
        {"uid": measurement_uid},
    )

    analysis = None
    if a:
        r = a[0]
        analysis = {
            "top_probe_analysis": r[0],
            "top_dns_failure": r[1],
            "top_tcp_failure": r[2],
            "top_tls_failure": r[3],
            "loni": {
                "dns": {"blocked": r[4], "down": r[5], "ok": r[6]},
                "tcp": {"blocked": r[7], "down": r[8], "ok": r[9]},
                "tls": {"blocked": r[10], "down": r[11], "ok": r[12]},
            },
        }

    fastpath = None
    if f:
        r = f[0]
        fastpath = {
            "anomaly": r[0] == "t",
            "confirmed": r[1] == "t",
            "msm_failure": r[2] == "t",
            "scores": r[3],
        }

    return {
        "measurement_uid": measurement_uid,
        "analysis": analysis,
        "fastpath": fastpath,
        "caveat": "The LoNI triple is hand-set and uncalibrated. It is shown "
                  "as a claim to check, not a reference answer.",
    }


# --------------------------------------------------------------------------
# Interval grain: the silent-time denominator
# --------------------------------------------------------------------------
#
# The event corpus is curated, so event recall is a coverage statement about a
# hand-built set. Nothing in it defines a week the detector should have been
# silent through, so the harness's "false alerts per series-week" had no frame
# behind it. This is that frame.
#
# The unit is the detector's own unit. `event_detector_cusums` keys on
# (probe_cc, probe_asn, domain), so anything coarser here would estimate a rate
# over a different population than the one the detector runs on.
#
# WHY THE STRATA PARTITION THE FRAME. The design note describes two draws — one
# over the intervals where the incumbent alerted, one random over covered
# cell-weeks. Taken literally they overlap: an alerted cell-week is also in the
# random stratum's population, so it has two selection probabilities and no
# single weight is correct for it. Here the strata are a partition instead, and
# `random_covered`'s predicate is resolved against the *set of strata being
# drawn* so the partition stays exhaustive whichever subset you ask for. That
# resolved predicate goes into the design spec, so a weight can never be
# reinterpreted under a different partition than the one it was drawn under.
#
# WHY THE ALERTED STRATUM IS NOT CIRCULAR. On its own it would be: it estimates
# the incumbent's precision conditional on having fired, which says nothing
# about quiet time, and a *candidate* detector's alerts in cells the incumbent
# never flagged would land on intervals nobody adjudicated. As a stratum with a
# recorded screen and a weight it is fine — the weight states how much of the
# frame it stands for. Note this uses the historical alert log as a screen; it
# does not replay the incumbent, which the harness cannot do anyway.

# ISO weeks: toStartOfWeek(t, 1) is Monday-based, matching the `x ISO week`
# unit. A partial week at either end of the frame is a shorter observation
# window with fewer measurements in it, which is not the same unit at all, so
# frames are snapped to whole weeks rather than truncated.
_WEEK = timedelta(days=7)

# Cell-weeks below this many measurements are not in the frame. Uniform draws
# over *all* cell-weeks are dominated by cells too thin for any detector to
# fire, and including them makes every detector score well by measuring mostly
# arithmetic. The floor is recorded in the spec and reported per volume band,
# so the exclusion is visible rather than baked in.
DEFAULT_VOLUME_FLOOR = 20

# Bands are derived from the measurement count on read, never entered — the
# same rule `ongoing` and `size_band` follow in the event grain. Edges are in
# the spec because they define what a per-band rate means.
VOLUME_BAND_EDGES = ((100, "low"), (1000, "medium"), (None, "high"))

INTERVAL_DESIGN_SCHEMA_VERSION = "1"


def volume_band(n: int) -> str:
    for edge, name in VOLUME_BAND_EDGES:
        if edge is None or n < edge:
            return name
    return VOLUME_BAND_EDGES[-1][1]


# The detector runs on the citizenlab global list plus twitter.com
# (`detector.get_domain_list`), so a frame over every domain would count quiet
# time in cells the detector never watches and flatter it for free. `detector`
# is the default for that reason; `all` is available for scoring a candidate
# with a wider remit, and which one was used is in the spec.
DETECTOR_DOMAINS_SQL = (
    "(domain IN (SELECT domain FROM citizenlab "
    "WHERE category_code = 'GRP' AND cc = 'ZZ') OR domain = 'twitter.com')"
)

# Cell key as a string on both sides of the alert join. The tuple form reads
# better but compares a UInt32 probe_asn against whatever width the other table
# declares, and a type mismatch there fails as an empty alerted set — which
# looks exactly like "the detector never fired", i.e. a wrong answer rather
# than an error.
_CELL_KEY = "concat({cc}, '|', toString({asn}), '|', {dom}, '|', toString({wk}))"

ALERTED_CELLS_SQL = f"""
    SELECT {_CELL_KEY.format(cc='probe_cc', asn='probe_asn', dom='domain',
                             wk='toStartOfWeek(ts, 1)')}
    FROM event_detector_changepoints
    WHERE ts >= %(since)s AND ts < %(until)s AND change_dir > 0
"""

_IS_ALERTED = (
    _CELL_KEY.format(cc="probe_cc", asn="probe_asn", dom="domain", wk="week")
    + f" IN ({ALERTED_CELLS_SQL})"
)

# `blocked_max` is the cell-week's loudest measurement. It is used to define
# the near-miss stratum and is NEVER returned to the client: it is a pipeline
# judgment, and on this grain it is close to the verdict itself.
INTERVAL_STRATA: Dict[str, Dict[str, Any]] = {
    "detector_alerted": {
        "predicate": _IS_ALERTED,
        "screen_kind": "incumbent_alert",
        "note": "Cell-weeks the deployed detector fired in. The historical "
                "alert log used as a screen, not replayed.",
    },
    "near_miss": {
        # Importance sampling, not a separate population: most random
        # cell-weeks are trivially quiet and carry almost no information per
        # minute of analyst time. Oversampling cells that had blocked-leaning
        # measurements without alerting is where the disagreements live, and
        # the weights correct for it. This is the whole reason to record a
        # design rather than draw uniformly.
        "predicate": f"NOT ({_IS_ALERTED}) AND blocked_max >= {BLOCKING_THRESHOLD}",
        "screen_kind": "near_miss_score",
        "note": "Did not alert, but something in the week scored "
                "blocked-leaning. Optional; when omitted these cells stay in "
                "random_covered.",
    },
    "random_covered": {
        # Resolved at draw time against the selected strata — see the note at
        # the top of this section.
        "predicate": None,
        "screen_kind": "volume_stratified_random",
        "note": "The denominator. Everything in the frame the other selected "
                "strata did not take.",
    },
}


def _resolve_interval_predicates(wanted: List[str]) -> Dict[str, str]:
    """Turn the selected strata into an exhaustive, disjoint partition.

    `random_covered` is the complement of whatever else was selected, so the
    frame is covered exactly once however the queue is composed. Drawing
    `near_miss` alone, with no complement stratum, is allowed and estimates
    nothing on its own — the weights say so, since the population it names is
    not the frame.
    """
    taken = [
        f"({INTERVAL_STRATA[s]['predicate']})"
        for s in ("detector_alerted", "near_miss")
        if s in wanted
    ]
    resolved = {
        s: INTERVAL_STRATA[s]["predicate"] for s in wanted if s != "random_covered"
    }
    if "random_covered" in wanted:
        resolved["random_covered"] = (
            " AND ".join(f"NOT {t}" for t in taken) if taken else "1"
        )
    return resolved


def _week_frame(since: Optional[datetime], until: Optional[datetime]):
    """Snap the frame to whole Monday-based weeks."""
    since_dt, until_dt = _frame(since, until)
    lo = since_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    lo -= timedelta(days=lo.weekday())
    if lo < since_dt:
        lo += _WEEK
    hi = until_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    hi -= timedelta(days=hi.weekday())
    if hi <= lo:
        raise HTTPException(
            400,
            "frame contains no whole ISO week — a partial week is a shorter "
            "observation window, not a smaller one",
        )
    return lo, hi


class IntervalRow(BaseModel):
    probe_cc: str
    probe_asn: int
    domain: str
    window_start: datetime
    window_end: datetime
    # From the coverage query, not a guess. The band is derived from it, and
    # the harness re-derives rather than trusting the stored band.
    measurements_in_window: int
    volume_band: str
    # sampling provenance, carried through to the label
    sampling_stratum: str
    sampling_weight: float
    sample_population: int
    sample_rows: int
    sampling_design_id: str
    screen_kind: str


class IntervalSampleResponse(BaseModel):
    design_id: str
    replicate: int
    spec: Dict[str, Any]
    frame_start: datetime
    frame_end: datetime
    strata: Dict[str, Dict[str, Any]]
    rows: List[IntervalRow]


@router.get("/interval_sample", response_model=IntervalSampleResponse)
def draw_interval_sample(
    db=Depends(get_clickhouse_session),
    strata: str = Query(
        "detector_alerted,random_covered",
        description="Comma-separated. Drawn separately and interleaved, so "
                    "the analyst cannot infer from a row's position whether "
                    "the incumbent alerted in it.",
    ),
    replicate: int = Query(
        1, ge=1,
        description="Independent draws of the same design. Same replicate = "
                    "same cell-weeks, so two analysts can be given an overlap "
                    "set without any coordination service.",
    ),
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    probe_cc: Optional[str] = Query(None, min_length=2, max_length=2),
    probe_asn: Optional[int] = None,
    domain: Optional[str] = None,
    domain_list: str = Query(
        "detector",
        description="'detector' restricts the frame to the domains the "
                    "deployed detector runs on; 'all' widens it. Counting "
                    "quiet time in cells nothing watches inflates the "
                    "denominator.",
    ),
    min_measurements: int = Query(
        DEFAULT_VOLUME_FLOOR, ge=1,
        description="Volume floor. Cell-weeks below it are not in the frame.",
    ),
    shares: Optional[str] = Query(
        None,
        description="Optional stratum=share pairs. Steers analyst effort "
                    "only — row weights stay population/drawn regardless.",
    ),
    limit: int = Query(40, ge=1, le=500),
) -> IntervalSampleResponse:
    """Draw cell-weeks to adjudicate.

    What the analyst decides about each is whether the state *changed* inside
    it, which is the only thing a changepoint detector can be right or wrong
    about. Two of the verdicts mean it did not — `quiet_observed` for a week
    where OONI saw nothing wrong, `blocked_throughout` for a week inside a
    block that started earlier — and both belong in the false-alarm
    denominator, because the detector should be silent in either.

    `quiet_observed`, never `quiet`: the week is judged from the same OONI data
    the detector reads, so an unmeasured block is indistinguishable from calm.
    That caps the claim at "no interference visible in OONI's data", which is
    the honest ceiling, and it is why a better candidate that finds subtle real
    events is not silently charged a false alarm.
    """
    since_dt, until_dt = _week_frame(since, until)
    wanted = sorted({s.strip() for s in strata.split(",") if s.strip()})
    unknown = [s for s in wanted if s not in INTERVAL_STRATA]
    if unknown:
        raise HTTPException(400, f"unknown strata: {unknown}")
    if not wanted:
        raise HTTPException(400, "no strata selected")
    if domain_list not in ("detector", "all"):
        raise HTTPException(400, "domain_list must be 'detector' or 'all'")

    predicates = _resolve_interval_predicates(wanted)

    scope_sql: List[str] = []
    scope_params: Dict[str, Any] = {}
    if probe_cc:
        scope_sql.append("probe_cc = %(probe_cc)s")
        scope_params["probe_cc"] = probe_cc.upper()
    if probe_asn:
        scope_sql.append("probe_asn = %(probe_asn)s")
        scope_params["probe_asn"] = probe_asn
    if domain:
        scope_sql.append("domain = %(domain)s")
        scope_params["domain"] = domain
    if domain_list == "detector":
        scope_sql.append(DETECTOR_DOMAINS_SQL)

    # Everything that changes which cell-weeks are eligible, or what a weight
    # means, is in the spec — including the resolved partition and the volume
    # floor, so two different frames can never collide onto one design id.
    spec = {
        "schema": INTERVAL_DESIGN_SCHEMA_VERSION,
        "grain": "interval",
        "unit": "probe_cc,probe_asn,domain x iso_week",
        "scoring_version": SCORING_VERSION,
        "blocking_threshold": BLOCKING_THRESHOLD,
        "strata": {
            s: {
                "predicate": predicates[s],
                "screen_kind": INTERVAL_STRATA[s]["screen_kind"],
            }
            for s in wanted
        },
        "frame": [since_dt.isoformat(), until_dt.isoformat()],
        "volume_floor": min_measurements,
        "volume_band_edges": [[e, n] for e, n in VOLUME_BAND_EDGES],
        "domain_list": domain_list,
        "scope": {
            "probe_cc": probe_cc.upper() if probe_cc else None,
            "probe_asn": probe_asn,
            "domain": domain,
        },
        "replicate": replicate,
    }
    derived_id = _design_fingerprint(spec)

    quotas = _quotas(wanted, shares, limit)

    # `blocked_max` costs three float columns over the whole frame and only the
    # near-miss stratum is defined in terms of it, so it is not read when that
    # stratum was not asked for.
    wants_blocked_max = "near_miss" in wanted

    # MUST not be run while a reprocess is in progress due to lack of FINAL
    # No test_name filter: the detector does not have one either, and the
    # frame has to be the population the detector actually runs over.
    cells_sql = f"""
        SELECT probe_cc,
               probe_asn,
               domain,
               toStartOfWeek(measurement_start_time, 1) AS week,
               count() AS n
               {", max(greatest(dns_blocked, tcp_blocked, tls_blocked)) AS blocked_max"
                if wants_blocked_max else ""}
        FROM analysis_web_measurement
        WHERE measurement_start_time >= %(since)s
          AND measurement_start_time < %(until)s
          {''.join(' AND ' + s for s in scope_sql)}
        GROUP BY probe_cc, probe_asn, domain, week
        HAVING n >= %(floor)s
    """

    # The strata are disjoint by construction (see
    # `_resolve_interval_predicates`), which is what lets one expression label
    # every cell-week in a single pass. Drawing each stratum under its own
    # WHERE meant re-running this GROUP BY once to size the population and
    # again to draw it — 2N aggregations of the same frame for N strata, and
    # that aggregation is the whole cost of the endpoint.
    #
    # `random_covered` is the fallback rather than a branch of its own: its
    # predicate is the negation of the others, so spelling it out would
    # evaluate the alerted-set lookup a second time. The lookup is hoisted to
    # an alias for the same reason — substituting the module constant into
    # itself, so it cannot match anything else by accident. The predicate text
    # recorded in the spec stays verbatim, since that text is what the design
    # id hashes.
    branches = ", ".join(
        f"({predicates[s].replace(_IS_ALERTED, 'is_alerted')}), '{s}'"
        for s in wanted
        if s != "random_covered"
    )
    fallback = "'random_covered'" if "random_covered" in wanted else "''"
    stratum_sql = f"multiIf({branches}, {fallback})" if branches else fallback
    # Drawing only the complement never asks about alerts, so in that case the
    # changepoint set is not built at all.
    alerted_sql = f"{_IS_ALERTED} AS is_alerted," if "is_alerted" in stratum_sql else ""

    # Per-stratum quotas, so an uneven `shares` split still takes exactly what
    # it was promised out of one shared ordering.
    quota_sql = "multiIf(" + ", ".join(
        f"stratum = '{s}', {int(quotas[s])}" for s in wanted
    ) + ", 0)"

    # Same salt the per-stratum draws used — `_design_fingerprint` plus the
    # stratum name — so a replicate drawn before this rewrite and one drawn
    # after select the same cell-weeks.
    order_sql = (
        "cityHash64(concat("
        + _CELL_KEY.format(cc="probe_cc", asn="probe_asn", dom="domain", wk="week")
        + ", %(design)s, ':', stratum))"
    )

    params: Dict[str, Any] = {
        "since": since_dt,
        "until": until_dt,
        "floor": min_measurements,
        "design": derived_id,
        **scope_params,
    }

    # NOTE: no blocked_max, no alert state, no changepoints leave this query.
    # The cell key, the window and how much data is in it — that is all an
    # analyst gets before committing.
    t0 = time.monotonic()
    rows = db.execute(
        f"""
        SELECT probe_cc, probe_asn, domain, week, n, stratum, population
        FROM (
            SELECT probe_cc, probe_asn, domain, week, n, stratum,
                   count() OVER (PARTITION BY stratum) AS population,
                   row_number() OVER (
                       PARTITION BY stratum ORDER BY {order_sql}
                   ) AS rn
            FROM (
                SELECT probe_cc, probe_asn, domain, week, n,
                       {alerted_sql}
                       {stratum_sql} AS stratum
                FROM ({cells_sql}) AS cells
            ) AS labelled
            WHERE stratum != ''
        ) AS ranked
        WHERE rn <= {quota_sql}
        ORDER BY stratum, rn
        """,
        params,
    )
    log.info("interval frame query: %.2fs", time.monotonic() - t0)

    # A stratum with a population draws at least one row (quotas floor at 1),
    # so an absent stratum here is an empty one and keeps its zero below.
    drawn: Dict[str, List[Any]] = {s: [] for s in wanted}
    populations: Dict[str, int] = {s: 0 for s in wanted}
    for r in rows:
        drawn[r[5]].append(r)
        populations[r[5]] = int(r[6])

    used: Dict[str, Dict[str, Any]] = {}
    buckets: List[List[IntervalRow]] = []

    for stratum in wanted:
        stratum_rows = drawn[stratum]
        population = populations[stratum]
        used[stratum] = {
            "predicate": predicates[stratum],
            "table": "analysis_web_measurement",
            "screen_kind": INTERVAL_STRATA[stratum]["screen_kind"],
            "population_estimate": population,
            "drawn": len(stratum_rows),
            "frame_start": since_dt.isoformat(),
            "frame_end": until_dt.isoformat(),
            "volume_floor": min_measurements,
            "scope": spec["scope"],
        }
        if not stratum_rows:
            continue
        buckets.append([
            IntervalRow(
                probe_cc=r[0] or "",
                probe_asn=int(r[1] or 0),
                domain=r[2] or "",
                window_start=datetime(r[3].year, r[3].month, r[3].day),
                window_end=datetime(r[3].year, r[3].month, r[3].day) + _WEEK,
                measurements_in_window=int(r[4]),
                volume_band=volume_band(int(r[4])),
                sampling_stratum=stratum,
                sampling_weight=population / len(stratum_rows),
                sample_population=population,
                sample_rows=len(stratum_rows),
                sampling_design_id=derived_id,
                screen_kind=INTERVAL_STRATA[stratum]["screen_kind"],
            )
            for r in stratum_rows
        ])

    interleaved: List[IntervalRow] = []
    for i in range(max((len(b) for b in buckets), default=0)):
        for b in buckets:
            if i < len(b):
                interleaved.append(b[i])

    return IntervalSampleResponse(
        design_id=derived_id,
        replicate=replicate,
        spec=spec,
        frame_start=since_dt,
        frame_end=until_dt,
        strata=used,
        rows=interleaved[:limit],
    )


@router.get("/interval_reveal")
def interval_reveal(
    probe_cc: str = Query(..., min_length=2, max_length=2),
    probe_asn: int = Query(...),
    domain: str = Query(...),
    window_start: datetime = Query(...),
    window_end: datetime = Query(...),
    pad_days: int = Query(7, ge=0, le=28),
    db=Depends(get_clickhouse_session),
) -> Dict[str, Any]:
    """What the detector did in this cell-week. Shown after commit, never
    before.

    Two things, because a bare alert flag is not diagnosable: the changepoints
    themselves, and the hourly signal the detector consumed to produce them.
    The signal is a median per cell-hour, exactly as `detector.get_observations`
    computes it, so an analyst who disagrees with an alert can see whether the
    detector saw something they did not or scored what they saw differently.
    """
    lo = window_start - timedelta(days=pad_days)
    hi = window_end + timedelta(days=pad_days)
    params = {
        "cc": probe_cc.upper(),
        "asn": probe_asn,
        "domain": domain,
        "lo": lo,
        "hi": hi,
        "ws": window_start,
        "we": window_end,
    }

    cps = db.execute(
        """
        SELECT ts, block_type, change_dir, s_pos, s_neg, current_state, h
        FROM event_detector_changepoints
        WHERE probe_cc = %(cc)s AND probe_asn = %(asn)s AND domain = %(domain)s
          AND ts >= %(lo)s AND ts < %(hi)s
        ORDER BY ts
        """,
        params,
    )

    # No FINAL here, unlike the sampler's frame query. This one is read to draw
    # a chart, not to size a population: an unmerged duplicate during a
    # reprocess nudges a median, where in the frame it would move a cell-week
    # into another volume band and corrupt a weight.
    signal = db.execute(
        """
        WITH IF(resolver_asn = probe_asn, 1, 0) AS is_isp_resolver
        SELECT toStartOfHour(measurement_start_time) AS ts,
               count() AS n,
               quantileIf(0.5)(dns_blocked, is_isp_resolver = 1) AS dns_isp_blocked,
               quantileIf(0.5)(dns_blocked, is_isp_resolver = 0) AS dns_other_blocked,
               quantile(0.5)(tcp_blocked) AS tcp_blocked,
               quantile(0.5)(tls_blocked) AS tls_blocked
        FROM analysis_web_measurement
        WHERE probe_cc = %(cc)s AND probe_asn = %(asn)s AND domain = %(domain)s
          AND measurement_start_time >= %(lo)s
          AND measurement_start_time < %(hi)s
        GROUP BY ts
        ORDER BY ts
        """,
        params,
    )

    changepoints = [
        {
            "ts": r[0],
            "block_type": r[1],
            "change_dir": int(r[2] or 0),
            "s_pos": r[3],
            "s_neg": r[4],
            "current_state": r[5],
            "h": r[6],
            # Whether it lands in the adjudicated week is the whole question,
            # so the client is not left to redo the comparison in local time.
            "in_window": window_start <= r[0].replace(tzinfo=None) < window_end,
        }
        for r in cps
    ]

    return {
        "probe_cc": probe_cc.upper(),
        "probe_asn": probe_asn,
        "domain": domain,
        "window_start": window_start,
        "window_end": window_end,
        "pad_days": pad_days,
        "changepoints": changepoints,
        "alerts_in_window": sum(
            1 for c in changepoints if c["in_window"] and c["change_dir"] > 0
        ),
        "signal": [
            {
                "ts": r[0],
                "count": int(r[1]),
                "dns_isp_blocked": r[2],
                "dns_other_blocked": r[3],
                "tcp_blocked": r[4],
                "tls_blocked": r[5],
            }
            for r in signal
        ],
        "caveat": "The deployed detector is online: this is the alert log it "
                  "actually emitted, under whatever state it carried at the "
                  "time. It is not a replay and cannot be reproduced from "
                  "this window alone.",
    }
