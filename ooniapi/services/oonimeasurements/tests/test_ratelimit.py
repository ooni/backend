import itertools
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from limits.aio.storage import RedisStorage

from oonimeasurements.common import rate_limit_quotas
from oonimeasurements.common.rate_limit_quotas import RateLimiterMiddleware


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
