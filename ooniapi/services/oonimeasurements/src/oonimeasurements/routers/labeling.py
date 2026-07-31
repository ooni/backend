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
   (design_id, stratum, frame, quota), and /sample returns the predicate it ran
   and the population it ran against, so the weights are reconstructable from
   the export alone. A weight is measured (population / drawn), never declared:
   any knob that only *describes* the sampling will eventually disagree with
   what the query did, and disagree silently.
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
        "predicate": "anomaly = 't' AND msm_failure = 'f'",
        "default_share": 0.40,
        "screen_kind": "fastpath_proxy",
        "note": "Proxy for B1's blocked-leaning-rule screen. LR numerator.",
    },
    "screen_negative": {
        "table": "fastpath",
        "predicate": "confirmed = 'f' AND anomaly = 'f' AND msm_failure = 'f'",
        "default_share": 0.35,
        "screen_kind": "fastpath_proxy",
        "note": "Bounds false negatives and carries the base rate. Small, "
                "and the first thing cut under pressure. Do not cut it.",
    },
    "fingerprint_match": {
        "table": "fastpath",
        "predicate": "confirmed = 't' AND msm_failure = 'f'",
        "default_share": 0.15,
        "screen_kind": "fingerprint",
        "note": "High-precision positives; tag the labels so LRs can be refit "
                "without them as a circularity check.",
    },
    "incident_window": {
        "table": "analysis_web_measurement",
        "predicate": "1",  # scoped entirely by the cc/domain/time params
        "default_share": 0.10,
        "screen_kind": "incident_scope",
        "note": "Draw inside a known event. Label the MEASUREMENT: rows here "
                "that are genuinely ok are the most valuable in the corpus.",
    },
}

# Bump when STRATA definitions or the fingerprint's shape change: it forces new
# design ids, so old weights are never silently reinterpreted under new rules.
# 2: rates became shares, and selection became ORDER BY hash + OFFSET.
DESIGN_SCHEMA_VERSION = "2"


def _fingerprint(spec: Dict[str, Any], prefix: str = "d") -> str:
    """Content-address a sampling design.

    The id is derived from the design so that there is never the same id used
    for two different parameter sets, leaving two incompatible weightings
    sharing a name.

    Redrawing with a higher limit returns a superset of the same rows, and two
    analysts who enter the same parameters get the same queue, which is how
    inter-rater agreement gets measured without any coordination service.

    Want genuinely fresh rows from the same population? Increment `replicate`.
    It is part of the spec, so it produces a different id and a draw that is
    disjoint from the previous one, on purpose and on the record.
    """
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":"), default=str)
    return prefix + hashlib.sha256(blob.encode()).hexdigest()[:10]


def _resolve_shares(
    wanted: List[str], override: Optional[str]
) -> Dict[str, float]:
    """Queue share per stratum, normalised over the strata actually asked for.

    `override` is "stratum=share,..." with shares in (0, 1]; unnamed strata keep
    their default. Normalising means dropping a stratum redistributes its share
    instead of quietly shrinking the queue, and it means the shares are readable
    as "what fraction of what I am about to label", which is the whole point.
    """
    shares = {s: float(STRATA[s]["default_share"]) for s in wanted}
    if override:
        for part in override.split(","):
            part = part.strip()
            if not part:
                continue
            key, _, val = part.partition("=")
            key = key.strip()
            if key not in shares:
                raise HTTPException(
                    400, f"share for unselected or unknown stratum: {key}"
                )
            try:
                share = float(val)
            except ValueError:
                raise HTTPException(400, f"share for {key} is not a number")
            if not 0 < share <= 1:
                raise HTTPException(400, f"share for {key} must be in (0, 1]")
            shares[key] = share

    total = sum(shares.values())
    if total <= 0:
        raise HTTPException(400, "shares sum to zero")
    return {s: v / total for s, v in shares.items()}


def _quotas(shares: Dict[str, float], limit: int) -> Dict[str, int]:
    """Turn shares into whole row counts that sum to exactly `limit`.

    Largest-remainder, so the rounding error lands on the biggest strata rather
    than starving a small one. Every selected stratum gets at least one row: a
    stratum present in the design but absent from the queue is indistinguishable
    from one that was never asked for, and `screen_negative` is small enough to
    be the one that vanishes.
    """
    order = sorted(shares)
    exact = {s: shares[s] * limit for s in order}
    base = {s: max(1, int(exact[s])) for s in order}

    # Give away, or claw back, whatever the flooring left over.
    drift = limit - sum(base.values())
    while drift != 0:
        step = 1 if drift > 0 else -1
        movable = [
            s for s in order
            if step > 0 or base[s] > 1  # never take a stratum below one row
        ]
        if not movable:
            break
        pick = max(
            movable,
            key=lambda s: (exact[s] - base[s]) * step,
        )
        base[pick] += step
        drift -= step
    return base


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
    sampling_weight: Optional[float]
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
    # Matches the UI's default. A wide frame is the point: rows are drawn in
    # hash order, not time order, so widening spreads the queue across the
    # period instead of concentrating it on last month.
    since = since or (until - timedelta(days=365))
    if since >= until:
        raise HTTPException(400, "since must be before until")
    return since, until


@router.get("/design")
def get_design() -> Dict[str, Any]:
    """The sampling design, verbatim.

    The UI copies this into the export so weights can be checked against the
    predicate that produced them. Edit a stratum here and you have a new
    design: bump design_id at draw time, never reuse it.
    """
    return {
        "strata": STRATA,
        "schema": DESIGN_SCHEMA_VERSION,
        "selection": "ORDER BY cityHash64(measurement_uid + design salt), "
                     "LIMIT quota OFFSET (replicate-1)*quota",
        "weighting": "population / drawn, per stratum",
    }


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
        description="Successive draws of the same design. Same replicate = "
                    "same rows (reproducible, extendable, comparable across "
                    "analysts). Increment it for rows the previous replicate "
                    "did not cover: replicates are disjoint by construction, "
                    "being successive slices of one deterministic ordering.",
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
    limit: int = Query(50, ge=1, le=500),
    shares: Optional[str] = Query(
        None,
        description="Override queue composition: 'screen_positive=0.5,"
                    "screen_negative=0.5'. Shares are normalised over the "
                    "selected strata, so they are fractions of your queue, not "
                    "sampling rates. Part of the design, so it changes the id.",
    ),
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
    share_by_stratum = _resolve_shares(wanted, shares)
    quota = _quotas(share_by_stratum, limit)

    resolved = {
        s: {
            "table": STRATA[s]["table"],
            "predicate": STRATA[s]["predicate"],
            "screen_kind": STRATA[s]["screen_kind"],
            "queue_share": round(share_by_stratum[s], 6),
            "quota": quota[s],
        }
        for s in wanted
    }
    # The population a draw addresses, and therefore what a weight means, is
    # fixed by everything except the replicate. Ordering is salted from that
    # part alone, so replicate 2 can take the next slice of the same ordering
    # rather than reshuffling into an independent (and overlapping) sample.
    population_spec = {
        "schema": DESIGN_SCHEMA_VERSION,
        "strata": resolved,
        "frame": [since_dt.isoformat(), until_dt.isoformat()],
        "scope": {
            "probe_cc": probe_cc.upper() if probe_cc else None,
            "probe_asn": probe_asn,
            "domain": domain,
            "test_names": tests or "all",
        },
    }
    spec = {**population_spec, "replicate": replicate}
    derived_id = _fingerprint(spec)
    order_salt = _fingerprint(population_spec, prefix="o")

    used: Dict[str, Dict[str, Any]] = {}
    buckets: List[List[SampleRow]] = []

    for stratum in wanted:
        spec_s = STRATA[stratum]
        table = spec_s["table"]

        where = [
            "measurement_start_time >= %(since)s",
            "measurement_start_time < %(until)s",
            f"({spec_s['predicate']})",
            # Only rows that can actually be labelled. The screens read
            # fastpath, but /candidate reads obs_web, so without this a draw
            # yields rows that 404 on open. It also keeps the weight honest:
            # `population` below counts the same set the draw samples from, and
            # rows missing from obs_web are missing non-randomly (they track
            # test and pipeline coverage), so excluding them from both is the
            # only way the ratio stays an inclusion probability.
            "measurement_uid IN ("
            "  SELECT measurement_uid FROM obs_web"
            "  WHERE measurement_start_time >= %(since)s"
            "    AND measurement_start_time < %(until)s"
            ")",
        ]
        params: Dict[str, Any] = {
            "since": since_dt,
            "until": until_dt,
            "salt": f"{order_salt}:{stratum}",
            "limit": quota[stratum],
            "offset": (replicate - 1) * quota[stratum],
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

        # Population first, because it *is* the weight. Not 1/share: the queue
        # is cut to a quota, so what a labelled row stands for is however many
        # eligible rows there were divided by however many were drawn. Taking
        # 20 of 5,000,000 makes each one worth 250,000, whatever share of the
        # queue the stratum was given.
        pop = db.execute(
            f"SELECT count() FROM {table} WHERE {where_sql}", params
        )
        population = int(pop[0][0]) if pop else 0

        resolver = (
            "resolver_asn" if table == "analysis_web_measurement" else "0"
        )
        # Ordering by a salted hash of the uid puts the eligible rows in a
        # deterministic pseudo-random order, so the first N are a uniform
        # sample of size N and OFFSET walks disjoint slices for successive
        # replicates. The salt has to be in the ORDER BY rather than in a
        # separate filter: unsalted, the same globally-low-hash measurements
        # sit at the head of every design's queue forever.
        #
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
            FROM {table}
            WHERE {where_sql}
            ORDER BY cityHash64(concat(measurement_uid, %(salt)s))
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        )

        # An empty stratum is not an error (a narrow scope, or a replicate past
        # the end of the population), but it has no weight either: dividing by
        # a zero draw would be a crash, and inventing a weight for rows that do
        # not exist would be worse.
        weight = (population / len(rows)) if rows else None

        used[stratum] = {
            "predicate": spec_s["predicate"],
            "table": table,
            "queue_share": resolved[stratum]["queue_share"],
            "quota": quota[stratum],
            "screen_kind": spec_s["screen_kind"],
            "population_estimate": population,
            "drawn": len(rows),
            "sampling_weight": weight,
            "exhausted": bool(rows) and len(rows) < quota[stratum],
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
                sampling_weight=weight,
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
    # EXCEPT, not SELECT *: obs_web carries `probe_analysis`, which is the
    # probe's own blocking verdict (web_connectivity's test_keys.blocking).
    # It is the same judgment /reveal exposes as top_probe_analysis, one row
    # down, and shipping it here would anchor the analyst against exactly what
    # the corpus exists to evaluate. Everything else is passed through, so the
    # client keeps field-matching across pipeline versions.
    obs = db.execute(
        """
        SELECT * EXCEPT (probe_analysis) FROM obs_web
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
