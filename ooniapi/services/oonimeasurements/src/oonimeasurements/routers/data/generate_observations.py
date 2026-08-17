"""
On-demand generation of observations from raw measurements.

When a measurement has not yet been processed by the pipeline, its
observations are missing from the obs_web table. In that case we can fetch
the raw measurement and run it through the oonipipeline transforms
(https://github.com/ooni/data) to generate the observations on the fly.
"""

import logging
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import ujson

try:
    from oonidata.dataclient import load_measurement
    from oonipipeline.netinfo import NetinfoDB
    from oonipipeline.transforms.observations import measurement_to_observations

    HAS_OONIPIPELINE = True
except ImportError:
    HAS_OONIPIPELINE = False

from ..v1.measurements import (
    _fetch_jsonl_measurement_body_clickhouse,
    _fetch_measurement_body_from_hosts,
)
from ...common.config import Settings

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_netinfodb(datadir: str) -> "NetinfoDB":
    Path(datadir).mkdir(parents=True, exist_ok=True)
    return NetinfoDB(datadir=Path(datadir), download=True)


def generate_observations(
    db, settings: Settings, measurement_uid: str
) -> List[Dict[str, Any]]:
    """
    Fetch the raw measurement for measurement_uid and run it through the
    oonipipeline transforms to generate its web observations on the fly.

    Returns a list of flattened dicts whose keys match the obs_web columns.
    Returns an empty list if oonipipeline is not installed or the raw
    measurement cannot be found.
    """
    if not HAS_OONIPIPELINE:
        log.warning(
            "oonipipeline is not installed, unable to generate observations on the fly"
        )
        return []

    body = _fetch_jsonl_measurement_body_clickhouse(
        db, measurement_uid, "ooni-data-eu-fra"
    ) or _fetch_measurement_body_from_hosts(settings.other_collectors, measurement_uid)
    if not body:
        log.info(f"unable to fetch raw measurement for {measurement_uid}")
        return []

    try:
        msmt = load_measurement(msmt=ujson.loads(body))
        msmt.measurement_uid = measurement_uid
        netinfodb = _get_netinfodb(settings.netinfodb_dir)
        observation_lists = measurement_to_observations(msmt, netinfodb=netinfodb)
    except Exception:
        log.error(
            f"failed to generate observations for {measurement_uid}", exc_info=True
        )
        return []

    rows = []
    for obs_list in observation_lists:
        for obs in obs_list:
            if getattr(obs, "__table_name__", None) != "obs_web":
                continue
            d = asdict(obs)
            d.update(d.pop("probe_meta", {}))
            d.update(d.pop("measurement_meta", {}))
            rows.append(d)
    return rows
