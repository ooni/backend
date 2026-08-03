"""
Labeling corpus API.

Read-only ClickHouse queries backing the measurement adjudication UI. There is
no write path: labels live in the analyst's browser and leave it by copy-paste,
so this router adds no storage, no auth surface, and no migration.

Two invariants this module exists to enforce:

1. BLINDING. /candidate returns what the probe and the control saw, and nothing
   the pipeline concluded. analysis_web_measurement and fastpath's anomaly /
   confirmed / scores columns are queried ONLY by /reveal, which the UI calls
   after the analyst has committed. If you add a field to /candidate, check it
   is not a pipeline judgment in disguise.

2. SAMPLING IS RECORDED, NOT REMEMBERED. Every draw is deterministic given
   (design_id, stratum, frame, rate), and /sample returns the predicate it ran
   and the population it ran against, so the weights are reconstructable from
   the export alone.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

# ooni/backend wires this up already; the import path is the one used by the
# existing data routers.
from ..dependencies import get_clickhouse_session  # type: ignore

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
        "predicate": "dns_blocked >= 0.5",
        "screen_kind": "loni_layer_proxy",
        "note": "DNS-attributed positives.",
    },
    "screen_tcp": {
        "table": "analysis_web_measurement",
        "predicate": "tcp_blocked >= 0.5 AND dns_blocked < 0.5",
        "screen_kind": "loni_layer_proxy",
        "note": "TCP-attributed positives, DNS quiet.",
    },
    "screen_tls": {
        "table": "analysis_web_measurement",
        "predicate": "tls_blocked >= 0.5 AND dns_blocked < 0.5 AND tcp_blocked < 0.5",
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
               countIf(greatest(dns_blocked, tcp_blocked, tls_blocked) >= 0.5)
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
