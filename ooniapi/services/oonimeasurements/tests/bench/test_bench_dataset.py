from datetime import timedelta

import pytest

from . import synthetic
from .conftest import EXTERNAL_URL, ROWS

pytestmark = pytest.mark.skipif(bool(EXTERNAL_URL), reason="checks the generated dataset")


def test_dataset_sizes(bench):
    counts = dict(bench.click.execute(
        "SELECT 'fastpath', count() FROM fastpath UNION ALL "
        "SELECT 'obs_web', count() FROM obs_web UNION ALL "
        "SELECT 'analysis_web_measurement', count() FROM analysis_web_measurement"
    ))
    assert counts == {
        "fastpath": ROWS,
        "obs_web": ROWS * 3,
        "analysis_web_measurement": ROWS * 7 // 10,
    }


@pytest.mark.parametrize("table", ["fastpath", "obs_web", "analysis_web_measurement"])
def test_dataset_covers_default_windows(bench, table):
    [(first, last)] = bench.click.execute(
        f"SELECT toDate(min(measurement_start_time)), toDate(max(measurement_start_time)) FROM {table}"
    )
    assert first == synthetic.ANCHOR_DATE - timedelta(days=synthetic.DAYS)
    assert last in (synthetic.ANCHOR_DATE - timedelta(days=1), synthetic.ANCHOR_DATE)


def test_dataset_measurement_uid_tracks_start_time(bench):
    # the uid prefix is the collection time; late uploads are rare but present
    [(late, total)] = bench.click.execute(
        "SELECT countIf(parseDateTimeBestEffort(substring(measurement_uid, 1, 14)) - measurement_start_time > 3600), count() FROM obs_web"
    )
    assert 0 < late / total < 0.05


def test_dataset_has_realistic_mix(bench):
    [(web, anomalies, countries)] = bench.click.execute(
        "SELECT countIf(test_name = 'web_connectivity') / count(), countIf(anomaly = 't') / count(), uniqExact(probe_cc) FROM fastpath"
    )
    # production: 84% web_connectivity, 8.6% anomalies, 145 countries a day
    assert 0.8 < web < 0.88
    assert 0.07 < anomalies < 0.10
    assert 100 < countries <= len(synthetic.COUNTRIES)
