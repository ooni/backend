import ujson
from clickhouse_driver import Client as ClickhouseClient

import oonimeasurements.routers.v1.measurements as measurements
from .utils import fake_get_bucket_url, getj


def test_log_comment_setting(client, db):
    getj(client, "/api/v1/measurements", params={"limit": 1})

    with ClickhouseClient.from_url(db) as ch:
        ch.execute("SYSTEM FLUSH LOGS")
        rows = ch.execute(
            """
            SELECT log_comment FROM system.query_log
            WHERE JSONExtractString(log_comment, 'handler') = 'GET /api/v1/measurements'
            AND type = 'QueryFinish'
            ORDER BY event_time_microseconds DESC LIMIT 1
            """
        )
    assert len(rows) == 1
    assert ujson.loads(rows[0][0]) == {
        "app_name": "oonimeasurements",
        "handler": "GET /api/v1/measurements",
    }


def test_log_comment_uses_route_template(client, db, monkeypatch, maybe_download_fixtures):
    """
    Use route template instead of actual path, so we can limit the log_comment
    size as much as possible
    """
    monkeypatch.setattr(measurements, "get_bucket_url", fake_get_bucket_url)

    # Taken from fixtures
    uid = "20250709075147.833477_US_webconnectivity_8f0e0b49950f2592"
    getj(client, f"/api/v1/measurement/{uid}")

    with ClickhouseClient.from_url(db) as ch:
        ch.execute("SYSTEM FLUSH LOGS")
        rows = ch.execute(
            """
            SELECT log_comment FROM system.query_log
            WHERE JSONExtractString(log_comment, 'handler') LIKE 'GET /api/v1/measurement/%'
            AND type = 'QueryFinish'
            ORDER BY event_time_microseconds DESC LIMIT 1
            """
        )
    assert len(rows) == 1
    assert ujson.loads(rows[0][0]) == {
        "app_name": "oonimeasurements",
        "handler": "GET /api/v1/measurement/{measurement_uid}",
    }
