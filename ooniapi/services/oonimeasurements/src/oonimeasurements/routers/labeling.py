"""
Labeling corpus API.

/sample draws from `labeling_frames`, a materialised frame table built by the
analysis-evaluation notebook: one row per measurement_uid in the frame window,
carrying what each pipeline concluded (`blocked_fastpath`, `blocked_analysis`)
and the stratum that pair puts it in.

* S11 both call it blocked
* S10 fastpath only
* S01_ok analysis only and msm_failure = 'f'
* S01_fail analysis only and msm_failure = 't'
* S00  neither

The query used to populate this table is the following:

INSERT INTO labeling_frames
SELECT
    COALESCE(a.measurement_uid, b.measurement_uid) as measurement_uid,
    a.blocked AS blocked_fastpath,
    b.blocked AS blocked_analysis,
    CASE
        WHEN blocked_fastpath AND blocked_analysis THEN 'S11'
        WHEN blocked_fastpath AND NOT blocked_analysis THEN 'S10'
        WHEN NOT blocked_fastpath AND blocked_analysis
           THEN IF(failed_fastpath, 'S01_fail', 'S01_ok')
        ELSE 'S00'
    END as stratum,
    'web_connectivity' as test_name,
     COALESCE(a.day, b.day) as day,
    'anomaly = \'t\' OR confirmed = \'t\'' as fastpath_query,
    'dns_blocked > 0.5 OR tls_blocked > 0.5 OR tls_blocked > 0.5' as analysis_query,
    COALESCE(a.failed_fastpath, FALSE) as failed_fastpath
FROM (
    SELECT
        measurement_uid,
        toStartOfDay(measurement_start_time) as day,
        IF(anomaly = 't' OR confirmed = 't', TRUE, FALSE) as blocked,
        IF(msm_failure = 't', TRUE, FALSE) as failed_fastpath
    FROM fastpath
    WHERE
        measurement_start_time > '2026-07-03'
        AND measurement_start_time < '2026-08-04'
        AND test_name = 'web_connectivity'
) a
FULL OUTER JOIN (
    SELECT
        measurement_uid,
        toStartOfDay(measurement_start_time) as day,
        IF(dns_blocked > 0.5 OR tls_blocked > 0.5 OR tls_blocked > 0.5, TRUE, FALSE) as blocked
    FROM analysis_web_measurement
    WHERE
        measurement_start_time > '2026-07-03'
        AND measurement_start_time < '2026-08-04'
        AND test_name = 'web_connectivity'
) b
USING (measurement_uid)
WHERE measurement_uid != ''
SETTINGS join_algorithm = 'grace_hash';
"""

import time
import hashlib
import json
import logging
import math
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

DESIGN_SCHEMA_VERSION = "3"

FRAME_TABLE = "labeling_frames"

# We divide
STRATA = ("S00", "S01_ok", "S01_fail", "S10", "S11")

# The stratums S10 and S01 are those in which the fastpath and data pipeline
# disagree, so they are the most valuable to sample. When they are in agreement
# is about blocking being present (S11) is of third important, while the rest is assigned
# to when they both think no blocking is happening (S00).
ALLOCATION: Dict[str, float] = {"S10": 0.3, "S01_ok": 0.15, "S01_fail": 0.15, "S11": 0.2}


def _allocate(sample_count: int) -> Dict[str, int]:
    """Target n_h per stratum. Floors, with the remainder going to S00."""
    targets = {s: math.floor(sample_count * f) for s, f in ALLOCATION.items()}
    targets["S00"] = sample_count - sum(targets.values())
    return {s: targets[s] for s in STRATA}


class QueueRow(BaseModel):
    measurement_uid: str
    test_name: str
    day: datetime
    strata: str
    draw_id: str
    blocked_fastpath: bool
    blocked_analysis: bool


class StratumDraw(BaseModel):
    strata: str
    N_h: int
    n_h: int
    n_h_target: int

class FrameInfo(BaseModel):
    table: str
    frame_version: str
    N_total: int
    N_h: Dict[str, int]
    day_start: datetime
    day_end: datetime
    test_names: List[str]
    fastpath_query: List[str]
    analysis_query: List[str]


class SampleResponse(BaseModel):
    draw_id: str
    draw_timestamp: datetime
    frame_version: str
    replicate: int
    sample_count: int
    spec: Dict[str, Any]
    frame: FrameInfo
    strata: Dict[str, StratumDraw]
    rows: List[QueueRow]


def _design_fingerprint(spec: Dict[str, Any], d) -> str:
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":"), default=str)
    return d + hashlib.sha256(blob.encode()).hexdigest()[:10]

def _frame(since: Optional[datetime], until: Optional[datetime]):
    until = until or datetime.now(timezone.utc).replace(tzinfo=None)
    since = since or (until - timedelta(days=30))
    if since >= until:
        raise HTTPException(400, "since must be before until")
    return since, until


def _frame_census(db) -> FrameInfo:
    """Snapshot the frame: its stratum counts and how it was defined.
    """
    rows = db.execute(
        f"""
        SELECT stratum,
               count() AS n,
               min(day) AS day_start,
               max(day) AS day_end,
               groupUniqArray(toString(test_name)) AS test_names,
               groupUniqArray(toString(fastpath_query)) AS fastpath_queries,
               groupUniqArray(toString(analysis_query)) AS analysis_queries
        FROM {FRAME_TABLE}
        GROUP BY stratum
        ORDER BY stratum
        """
    )
    if not rows:
        raise HTTPException(
            503,
            f"{FRAME_TABLE} is empty: build the frame before drawing from it",
        )

    descriptor = {
        "table": FRAME_TABLE,
        "N_total": sum(int(r[1]) for r in rows),
        "N_h": {r[0]: int(r[1]) for r in rows},
        "day_start": min(r[2] for r in rows),
        "day_end": max(r[3] for r in rows),
        "test_names": sorted({t for r in rows for t in r[4]}),
        "fastpath_query": sorted({q for r in rows for q in r[5]}),
        "analysis_query": sorted({q for r in rows for q in r[6]}),
    }
    missing = [s for s in STRATA if s not in descriptor["N_h"]]
    if missing:
        # Not fatal — an empty stratum is a real state of the world — but it
        # means those quotas cannot be filled, so say so once, loudly.
        log.warning("frame %s has no rows in strata %s", FRAME_TABLE, missing)
    return FrameInfo(frame_version=_design_fingerprint(descriptor, "f"), **descriptor)


@router.get("/sample", response_model=SampleResponse)
def draw_sample(
    db=Depends(get_clickhouse_session),
    replicate: int = Query(
        1, ge=1,
        description="Independent draws of the same design. Same replicate = "
                    "same rows (reproducible, extendable, comparable across "
                    "analysts).",
    ),
    sample_count: int = Query(
        100, ge=1, le=5000,
        description="how many measurement_uids should be sampled",
    )
) -> SampleResponse:
    started = time.monotonic()
    frame = _frame_census(db)
    targets = _allocate(sample_count)

    # The salt fixes each uid's rank within its stratum.
    salt = f"{FRAME_TABLE}:{DESIGN_SCHEMA_VERSION}:r{replicate}"

    spec = {
        "schema": DESIGN_SCHEMA_VERSION,
        "frame_table": FRAME_TABLE,
        "frame_version": frame.frame_version,
        "allocation": targets,
        "sample_count": sample_count,
        "replicate": replicate,
        "salt": salt,
    }
    draw_id = _design_fingerprint(spec, "dr")

    query = f"""
    SELECT measurement_uid,
           blocked_fastpath,
           blocked_analysis,
           stratum,
           test_name,
           day
    FROM {FRAME_TABLE}
    WHERE stratum = %(stratum)s
    ORDER BY cityHash64(concat(measurement_uid, %(salt)s)), measurement_uid
    LIMIT %(limit)s
    """

    used: Dict[str, StratumDraw] = {}
    buckets: List[List[QueueRow]] = []

    for stratum in STRATA:
        target = targets[stratum]
        rows = (
            db.execute(query, {"stratum": stratum, "salt": salt, "limit": target})
            if target
            else []
        )
        population = frame.N_h.get(stratum, 0)
        n_h = len(rows)
        if n_h < target:
            log.warning(
                "draw %s: stratum %s wanted %d, frame had %d",
                draw_id, stratum, target, population,
            )
        used[stratum] = StratumDraw(
            strata=stratum,
            N_h=population,
            n_h=n_h,
            n_h_target=target,
        )
        buckets.append([
            QueueRow(
                measurement_uid=r[0],
                test_name=r[4] or "",
                strata=r[3],
                blocked_fastpath=bool(r[1]),
                blocked_analysis=bool(r[2]),
                day=r[5],
                draw_id=draw_id,
            )
            for r in rows
        ])

    # Interleave rather than concatenate. A queue that runs all the positives
    # first tells the analyst which stratum they are in, which is most of the
    # way to telling them the answer.
    interleaved: List[QueueRow] = []
    for i in range(max((len(b) for b in buckets), default=0)):
        for b in buckets:
            if i < len(b):
                interleaved.append(b[i])

    log.info(
        "draw %s: %d rows from frame %s in %.1fs",
        draw_id, len(interleaved), frame.frame_version, time.monotonic() - started,
    )
    return SampleResponse(
        draw_id=draw_id,
        draw_timestamp=datetime.now(timezone.utc),
        frame_version=frame.frame_version,
        replicate=replicate,
        sample_count=sample_count,
        spec=spec,
        frame=frame,
        strata=used,
        rows=interleaved,
    )
