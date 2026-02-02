from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from oonimeasurements.common.rate_limit_quotas import RateLimiterMiddleware


@pytest.mark.asyncio
async def test_endpoint_limit(redis_server, app):
    app.add_middleware(
        RateLimiterMiddleware,
        redis_url=redis_server,
        limits="10000/day;13000/7day",
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
                print(resp.headers["X-RateLimit-Remaining"])
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
