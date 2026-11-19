import itertools
import secrets
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from clickhouse_driver import Client as ClickhouseClient
from limits.aio.storage import RedisStorage

from oonimeasurements.common import rate_limit_quotas
from oonimeasurements.common.clickhouse_utils import query_click
from oonimeasurements.common.apiauth.tokens import TOKEN_PREFIX, hash_token
from oonimeasurements.common.rate_limit_quotas import RateLimiterMiddleware

from .utils import get_postgresql_url


@pytest.mark.asyncio
async def test_endpoint_limit(valkey_server, app):
    storage = RedisStorage(valkey_server)
    await storage.reset()
    app.add_middleware(
        RateLimiterMiddleware,
        valkey_url=valkey_server,
        rate_limits="10000/day;13000/7day",
        unmetered_pages=[r"/version"],
    )

    mock_current_time = [0]

    def mock_monotonic():
        mock_current_time[0] += 10
        return mock_current_time[0]

    @app.get("/quotatest")
    async def quotatest():
        return {"quota": "test"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        with patch("time.perf_counter", side_effect=mock_monotonic):
            resp = await client.get(
                "/quotatest", headers={"X-Forwarded-For": "127.0.0.1"}
            )
            assert resp.status_code == 200
            assert resp.json() == {"quota": "test"}
            initial_quota = int(resp.headers["X-RateLimit-Remaining"])
            assert initial_quota > 0

            for i in range(int(initial_quota / 1000)):
                resp = await client.get(
                    "/quotatest", headers={"X-Forwarded-For": "127.0.0.1"}
                )
                assert int(resp.headers["X-RateLimit-Remaining"]) < initial_quota
                assert resp.status_code == 200

            resp = await client.get(
                "/quotatest", headers={"X-Forwarded-For": "127.0.0.1"}
            )
            assert resp.status_code == 429

            resp = await client.get(
                "/version", headers={"X-Forwarded-For": "127.0.0.1"}
            )
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_10_per_minute(valkey_server, app):
    storage = RedisStorage(valkey_server)
    await storage.reset()
    app.add_middleware(
        RateLimiterMiddleware,
        valkey_url=valkey_server,
        rate_limits="10/minute;10000/day;13000/7day",
        whitelisted_ipaddrs=["123.45.6.7"],
    )

    @app.get("/slow_response")
    async def slow_response():
        return {"quota": "test"}

    # The middleware charges 1 unit per 10 ms of request time, so with the
    # real clock a slow CI runner could charge 4 or 5 units per request and
    # use up the 10/minute quota in three. Its clock here advances 25 ms
    # between a request's start and its response: every request costs 2.
    clock = itertools.count(step=0.025)
    fake_time = SimpleNamespace(perf_counter=lambda: next(clock))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        with patch.object(rate_limit_quotas, "time", fake_time):
            for expected in (8, 6, 4):
                resp = await client.get(
                    "/slow_response", headers={"X-Forwarded-For": "127.0.0.1"}
                )
                assert resp.status_code == 200
                assert int(resp.headers["X-RateLimit-Remaining"]) == expected

        for _ in range(5):
            resp = await client.get(
                "/version", headers={"X-Forwarded-For": "123.45.6.7"}
            )
            # no rate limit, no header
            assert "x-ratelimit-remaining" not in resp.headers.keys()
            assert resp.status_code == 200


def add_token(postgresql, user_id: str, expires_at=None) -> str:
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    postgresql.execute(
        "INSERT INTO apitoken (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (hash_token(token), user_id, expires_at),
    )
    postgresql.commit()
    return token


def get_token_usage(clickhouse_url: str, user_id: str):
    with ClickhouseClient.from_url(clickhouse_url) as click:
        click.execute("SYSTEM FLUSH ASYNC INSERT QUEUE")
        return query_click(
            click,
            "SELECT method, route, status_code, token_hash_prefix FROM api_token_usage WHERE user_id = %(user_id)s",
            {"user_id": user_id},
        )


def test_api_token_unlimited_and_recorded(token_app, client, postgresql, db):
    user_id = "user-" + secrets.token_hex(4)
    token = add_token(postgresql, user_id)
    headers = {"Authorization": f"Bearer {token}"}

    for i in range(5):
        resp = client.get(f"/tokentest/{i}", headers=headers)
        assert resp.status_code == 200
        assert "x-ratelimit-remaining" not in resp.headers

    rows = get_token_usage(db, user_id)
    assert len(rows) == 5
    for row in rows:
        assert row == {
            "method": "GET",
            "route": "/tokentest/{param}",
            "status_code": 200,
            "token_hash_prefix": hash_token(token)[:8],
        }


def test_api_token_invalid(token_app, client, postgresql):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    future = datetime.now(timezone.utc) + timedelta(days=1)
    expired = add_token(postgresql, "expired-user", expires_at=past)
    valid = add_token(postgresql, "valid-user", expires_at=future)

    for token in (expired, TOKEN_PREFIX + "unknown"):
        resp = client.get("/tokentest/x", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    resp = client.get("/tokentest/x", headers={"Authorization": f"Bearer {valid}"})
    assert resp.status_code == 200

    # Revoking is picked up once the cache entry expires (ttl=0 here)
    postgresql.execute(
        "UPDATE apitoken SET expires_at = %s WHERE token_hash = %s",
        (past, hash_token(valid)),
    )
    postgresql.commit()
    resp = client.get("/tokentest/x", headers={"Authorization": f"Bearer {valid}"})
    assert resp.status_code == 401


def test_non_api_token_bearer_uses_ip_limits(token_app, client):
    resp = client.get(
        "/tokentest/x",
        headers={
            "Authorization": "Bearer some.jwt.token",
            # A fresh address, so no quota is left over from other tests
            "X-Forwarded-For": "10.0.0." + secrets.token_hex(4),
        },
    )
    assert resp.status_code == 200
    assert "x-ratelimit-remaining" in resp.headers


def test_api_token_db_down(app, client, valkey_server):
    """
    If unable to authenticate tokens, return a server error
    """
    app.add_middleware(
        RateLimiterMiddleware,
        valkey_url=valkey_server,
        postgresql_url="postgresql://bad:bad@localhost:1/bad",
    )

    resp = client.get("/version", headers={"Authorization": f"Bearer {TOKEN_PREFIX}abc"})
    assert resp.status_code == 503


def test_api_token_cached(app, client, valkey_server, postgresql):
    """
    Due to our cache implementation, some requests might pass even when the
    tokens are expired or removed.

    This test documents that behavior.
    """
    app.add_middleware(
        RateLimiterMiddleware,
        valkey_url=valkey_server,
        postgresql_url=get_postgresql_url(postgresql),
        api_token_cache_ttl=60,
    )
    token = add_token(postgresql, "cached-user")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/version", headers=headers)
    assert resp.status_code == 200

    # Served from memory even after the token is gone from the database
    postgresql.execute("DELETE FROM apitoken WHERE token_hash = %s", (hash_token(token),))
    postgresql.commit()
    resp = client.get("/version", headers=headers)
    assert resp.status_code == 200
