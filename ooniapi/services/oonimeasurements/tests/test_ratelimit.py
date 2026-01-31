from unittest.mock import patch

from fastapi.testclient import TestClient

from oonimeasurements.common.rate_limit_quotas import RateLimiterMiddleware


def test_endpoint_limit(redis_server, app):
    app.add_middleware(RateLimiterMiddleware, redis_url=redis_server)

    mock_current_time = [0]

    def mock_perf_counter():
        mock_current_time[0] += 42
        return mock_current_time[0]

    @app.get("/quotatest")
    async def quotatest():
        return {"quota": "test"}

    with patch("time.perf_counter", side_effect=mock_perf_counter):
        client = TestClient(app)
        resp = client.get("/quotatest", headers={"X-Forwarded-For": "127.0.0.1"})
        assert resp.status_code == 200
        assert resp.json() == {"quota": "test"}
        initial_quota = int(resp.headers["X-RateLimit-Remaining"])
        assert initial_quota > 0

        for i in range(10):
            resp = client.get("/quotatest", headers={"X-Forwarded-For": "127.0.0.1"})
            assert int(resp.headers["X-RateLimit-Remaining"]) < initial_quota
