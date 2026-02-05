import asyncio
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from limits.aio.storage import RedisStorage

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
    )

    @app.get("/slow_response")
    async def slow_response():
        await asyncio.sleep(0.02)
        return {"quota": "test"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        prev_quota = 10
        for i in range(3):
            resp = await client.get(
                "/slow_response", headers={"X-Forwarded-For": "127.0.0.1"}
            )
            limit_remaining = int(resp.headers["X-RateLimit-Remaining"])
            assert (prev_quota - limit_remaining) > 1
            assert resp.status_code == 200
            prev_quota = limit_remaining
