import pytest
from fastapi.testclient import TestClient

from oonimeasurements.common.rate_limit_quotas import RateLimiterMiddleware
from oonimeasurements.main import app, lifespan


def test_endpoint_limit(redis_server):
    print(redis_server)

    @app.get("/quotatest")
    async def quotatest():
        return {"quota": "test"}

    app.add_middleware(
        RateLimiterMiddleware, redis_url=redis_server, quotatest_pages=["/quotatest"]
    )

    client = TestClient(app)
    resp = client.get("/quotatest", headers={"X-Forwarded-For": "127.0.0.1"})
    assert resp.status_code == 200
    assert resp.json() == {"quota": "test"}
    initial_quota = int(resp.headers["X-RateLimit-Remaining"])
    assert initial_quota > 0

    for i in range(10):
        resp = client.get("/quotatest", headers={"X-Forwarded-For": "127.0.0.1"})
        assert int(resp.headers["X-RateLimit-Remaining"]) < initial_quota
