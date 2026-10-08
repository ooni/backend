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
        whitelisted_ipaddrs=["123.45.6.7"],
    )

    @app.get("/slow_response")
    async def slow_response():
        await asyncio.sleep(0.02)
        return {"quota": "test"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        prev_quota = 10
        for _ in range(3):
            resp = await client.get(
                "/slow_response", headers={"X-Forwarded-For": "127.0.0.1"}
            )
            limit_remaining = int(resp.headers["X-RateLimit-Remaining"])
            assert (prev_quota - limit_remaining) > 1
            assert resp.status_code == 200
            prev_quota = limit_remaining

        for _ in range(5):
            resp = await client.get(
                "/version", headers={"X-Forwarded-For": "123.45.6.7"}
            )
            # no rate limit, no header
            assert "x-ratelimit-remaining" not in resp.headers.keys()
            assert resp.status_code == 200


def _client_ipaddr(xff=None, client=("10.0.0.1", 1234), **kwargs):
    middleware = RateLimiterMiddleware(app=None, valkey_url="memory", **kwargs)
    headers = [(b"x-forwarded-for", v.encode()) for v in (xff or [])]
    scope = {"type": "http", "method": "GET", "path": "/", "headers": headers, "client": client}
    return middleware.get_client_ipaddr(scope, None)


def test_client_ipaddr_is_the_address_appended_by_the_proxy():
    # the ALB (xff_header_processing.mode = append) and the gateway append
    # the address they saw to whatever X-Forwarded-For the client sent
    assert _client_ipaddr(["198.51.100.7"]) == "198.51.100.7"
    assert _client_ipaddr(["203.0.113.9, 198.51.100.7"]) == "198.51.100.7"
    # several X-Forwarded-For headers count as one list, in order
    assert _client_ipaddr(["203.0.113.9", "198.51.100.7"]) == "198.51.100.7"
    # without the header, the peer address
    assert _client_ipaddr() == "10.0.0.1"


def test_client_ipaddr_skips_trusted_proxies():
    # a request forwarded by another proxy (e.g. the legacy API host) before
    # the ALB: skip the proxies we trust, from the right
    xff = ["203.0.113.9, 192.0.2.10"]
    assert _client_ipaddr(xff) == "192.0.2.10"
    assert _client_ipaddr(xff, trusted_proxies=["192.0.2.10"]) == "203.0.113.9"
    assert _client_ipaddr(xff, trusted_proxies=["192.0.2.0/24"]) == "203.0.113.9"


def test_whitelist_applies_to_the_appended_address_only():
    middleware = RateLimiterMiddleware(app=None, valkey_url="memory", whitelisted_ipaddrs=["5.9.112.244"])
    scope = {"type": "http", "method": "GET", "path": "/", "client": ("10.0.0.1", 1234),
             "headers": [(b"x-forwarded-for", b"5.9.112.244, 198.51.100.7")]}
    assert middleware.get_client_ipaddr(scope, None) == "198.51.100.7"
    assert not middleware.is_ip_whitelisted("198.51.100.7")


def test_client_ipaddr_fails_on_an_entry_our_proxy_should_not_write():
    from oonimeasurements.common.utils import InvalidForwardedFor
    # e.g. the ALB's xff_client_port setting turned on
    with pytest.raises(InvalidForwardedFor):
        _client_ipaddr(["203.0.113.9, 198.51.100.7:51234"])
    # a chain of only trusted proxies doesn't say who the client is
    with pytest.raises(InvalidForwardedFor):
        _client_ipaddr(["192.0.2.10"], trusted_proxies=["192.0.2.0/24"])
