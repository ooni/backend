"""
API token lookups run on threads of their own (ThreadBudget), not on the
worker threads that the endpoints and their ClickHouse queries share. These
tests need no database: the lookup is replaced by a function that sleeps.
tests/threadpool/ has the load test against real Postgres and ClickHouse.
"""

import asyncio
import secrets
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from oonimeasurements.common.apiauth.tokens import ApiTokenCache, ThreadBudget
from oonimeasurements.common.rate_limit_quotas import RateLimiterMiddleware


def make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/sync")
    def sync_endpoint():
        # A sync endpoint runs on one of the shared worker threads
        return {"ok": True}

    app.add_middleware(
        RateLimiterMiddleware,
        valkey_url="memory",
        # Never connected to: lookups are replaced in each test
        postgresql_url="postgresql://nobody@127.0.0.1:1/nothing",
    )
    return app


def token_request(client, token, i):
    # Each request from its own address, so the IP quota doesn't apply
    headers = {"X-Forwarded-For": f"10.1.{i // 250}.{i % 250 + 1}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.get("/sync", headers=headers)


@pytest.mark.asyncio
async def test_hung_lookups_leave_the_shared_threads_free(monkeypatch):
    # As with Postgres hung: every lookup blocks its thread
    monkeypatch.setattr(ApiTokenCache, "_fetch", lambda self, h: time.sleep(1.5))
    app = make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        # More made-up tokens than the 40 shared threads
        attack = [
            asyncio.create_task(token_request(client, "ooni_" + secrets.token_hex(8), i))
            for i in range(60)
        ]
        await asyncio.sleep(0.2)

        start = time.monotonic()
        r = await token_request(client, None, 1000)
        elapsed = time.monotonic() - start
        await asyncio.gather(*attack)

    assert r.status_code == 200
    # Before ThreadBudget, this waited for the lookups' 1.5 s
    assert elapsed < 0.5


@pytest.mark.asyncio
async def test_parallel_requests_with_a_new_token_all_succeed(monkeypatch):
    # A healthy database: lookups take 50 ms
    def fetch(self, token_hash):
        time.sleep(0.05)
        return SimpleNamespace(user_id="tester", expires_at=None)

    monkeypatch.setattr(ApiTokenCache, "_fetch", fetch)
    app = make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        # More parallel requests than the budget's threads, none cached yet
        responses = await asyncio.gather(
            *(token_request(client, "ooni_valid", i) for i in range(30))
        )
    assert [r.status_code for r in responses] == [200] * 30


@pytest.mark.asyncio
async def test_thread_budget_runs_at_most_size_calls_at_once():
    budget = ThreadBudget(size=2, timeout=5)
    running, most = 0, 0
    lock = threading.Lock()

    def call():
        nonlocal running, most
        with lock:
            running += 1
            most = max(most, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return "done"

    results = await asyncio.gather(*(budget.run(call) for _ in range(10)))
    assert results == ["done"] * 10
    assert most == 2


@pytest.mark.asyncio
async def test_thread_budget_times_out_waiting_for_a_thread():
    budget = ThreadBudget(size=1, timeout=0.3)
    stuck = asyncio.create_task(budget.run(time.sleep, 1))
    await asyncio.sleep(0.05)

    start = time.monotonic()
    with pytest.raises(TimeoutError):
        await budget.run(lambda: "never runs")
    assert time.monotonic() - start < 0.6

    # The running call isn't interrupted: it returns when it's done
    assert await stuck is None
    assert await budget.run(lambda: "free again") == "free again"
