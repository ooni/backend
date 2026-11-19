import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

from clickhouse_driver import Client as Clickhouse
from limits import parse_many as parse_many_limits
from limits.aio.storage import MemoryStorage, RedisStorage
from limits.aio.strategies import MovingWindowRateLimiter
from prometheus_client import Counter, Histogram
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .apiauth.tokens import TOKEN_PREFIX, ApiTokenCache, CachedToken

log = logging.getLogger(__name__)

## We convert the previous limits by multiplying by 100, since they were previously expressed as seconds of runtime per period. Now we are expressing cost as the number of 10ms.
# ipaddr_per_month=60000,
# ipaddr_per_week=20000,
# ipaddr_per_day=4000,

DEFAULT_LIMITS = "10/minute;400000/day;200000/7day"

## Metrics
RATE_LIMIT_HITS = Counter(
    "rate_limit_hits",
    "The number of requests that triggered a rate limit",
    ["auth"],
)

REQUEST_DURATION = Histogram(
    "rate_limit_request_duration",
    "The duration of requests not triggered by a rate limit",
    ["auth"],
)

RATE_LIMIT_OVERHEAD = Histogram(
    "rate_limit_overhead_seconds",
    "Time spent by the rate limiter itself, excluding the request",
    ["auth", "phase"],
)

RATE_LIMIT_REQUESTS = Counter(
    "rate_limit_requests",
    "Requests going through the rate limiter, by authentication type",
    ["auth"],
)

API_TOKEN_REJECTED = Counter(
    "api_token_rejected",
    "Requests rejected because of an unknown or expired API token",
)

API_TOKEN_LOOKUP_ERRORS = Counter(
    "api_token_lookup_errors",
    "Failures looking up an API token in the database",
)

API_TOKEN_USAGE_ERRORS = Counter(
    "api_token_usage_errors",
    "Failures recording API token usage in clickhouse",
)


def hash_ipaddr(ipaddr: str, key: str) -> str:
    return hashlib.blake2b(
        ipaddr.encode(), key=key.encode("utf-8"), digest_size=8
    ).hexdigest()


def insert_token_usage(clickhouse_url: str, row: dict) -> None:
    db = Clickhouse.from_url(clickhouse_url)
    try:
        db.execute(
            "INSERT INTO api_token_usage "
            "(ts, user_id, token_hash_prefix, method, route, status_code, cost) VALUES",
            [row],
            types_check=True,
            # Don't wait for the data to be written, clickhouse batches it
            settings={"async_insert": 1, "wait_for_async_insert": 0},
        )
    finally:
        db.disconnect()


class RateLimiterMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        valkey_url: str,
        hashing_key: str = "CHANGEME",
        rate_limits: str = DEFAULT_LIMITS,
        whitelisted_ipaddrs: List[str] = [],
        unmetered_pages: List[str] = [],
        postgresql_url: Optional[str] = None,
        clickhouse_url: Optional[str] = None,
        api_token_cache_ttl: int = 60,
    ):
        self.app = app
        self._unmetered_pages_globs = set()
        self._unmetered_pages = set()
        for p in unmetered_pages:
            if p.endswith("*"):
                self._unmetered_pages_globs.add(p.rstrip("*"))
            else:
                self._unmetered_pages.add(p)

        self.whitelisted_ipaddrs = whitelisted_ipaddrs
        if valkey_url.startswith("memory"):
            self.limits_storage = MemoryStorage()
        else:
            self.limits_storage = RedisStorage(f"async+{valkey_url}")
        self.limiter = MovingWindowRateLimiter(self.limits_storage)
        self.rate_limits = parse_many_limits(rate_limits)
        self.hashing_key = hashing_key

        # API tokens are disabled when there's no database to look them up
        self.token_cache = (
            ApiTokenCache(postgresql_url, api_token_cache_ttl)
            if postgresql_url
            else None
        )
        self.clickhouse_url = clickhouse_url

    def get_client_ipaddr(self, scope: Scope, receive: Receive) -> str:
        request = Request(scope, receive)

        headers = Headers(scope=scope)
        x_forwarded_for = headers.get("X-Forwarded-For")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        return request.client.host

    def get_api_token(self, scope: Scope) -> Optional[str]:
        """
        Returns the API token from the Authorization header. Other bearer
        tokens (eg. JWTs) are ignored
        """
        if self.token_cache is None:
            return None
        authorization = Headers(scope=scope).get("Authorization", "")
        if not authorization.startswith("Bearer " + TOKEN_PREFIX):
            return None
        return authorization[len("Bearer ") :]

    def is_unmetered_page(self, path: str) -> bool:
        if path in self._unmetered_pages:
            return True
        for u in self._unmetered_pages_globs:
            if path.startswith(u):
                return True
        return False

    def is_ip_whitelisted(self, ipaddr: str) -> bool:
        return ipaddr in self.whitelisted_ipaddrs

    async def consume_rate_limits(self, ipaddr: str, cost=1) -> bool:
        for rl in self.rate_limits:
            allowed = await self.limiter.hit(rl, "ooniapi:ipaddr", ipaddr, cost=cost)
            if not allowed:
                return False
        return True

    async def get_min_available_quota(self, ipaddr: str) -> int:
        quotas = []
        for rl in self.rate_limits:
            _, remaining = await self.limiter.get_window_stats(
                rl, "ooniapi:ipaddr", ipaddr
            )
            quotas.append(remaining)
        return min(quotas)

    def should_ratelimit(self, scope: Scope, ipaddr: str) -> bool:
        if self.is_ip_whitelisted(ipaddr):
            return False

        if self.is_unmetered_page(scope["path"]):
            return False

        return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover
            return await self.app(scope, receive, send)

        ipaddr = self.get_client_ipaddr(scope, receive)

        if not self.should_ratelimit(scope, ipaddr):
            return await self.app(scope, receive, send)

        token = self.get_api_token(scope)
        if token is not None:
            return await self.handle_token_request(token, scope, receive, send)

        RATE_LIMIT_REQUESTS.labels(auth="ip").inc()
        request_start = time.perf_counter()

        hashed_ipaddr = hash_ipaddr(ipaddr, self.hashing_key)
        with RATE_LIMIT_OVERHEAD.labels(auth="ip", phase="check").time():
            remaining = await self.get_min_available_quota(hashed_ipaddr)
        if remaining <= 0:
            RATE_LIMIT_HITS.labels(auth="ip").inc()
            headers = MutableHeaders(scope=scope)
            headers.append("X-RateLimit-Remaining", "0")
            response = JSONResponse({"error": "quota exceeded"}, 429, headers=headers)
            return await response(scope, receive, send)

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                tdelta = time.perf_counter() - request_start
                REQUEST_DURATION.labels(auth="ip").observe(tdelta)
                # Cost is calculated by assuming 10ms of request time is 1 unit
                # rounded to 1 when it's less than 10ms
                cost = max([int(tdelta * 100), 1])
                with RATE_LIMIT_OVERHEAD.labels(auth="ip", phase="consume").time():
                    await self.consume_rate_limits(hashed_ipaddr, cost=cost)
                headers = MutableHeaders(scope=message)
                headers.append("X-RateLimit-Remaining", str(max([remaining - cost, 0])))
            await send(message)

        await self.app(scope, receive, wrapped_send)

    async def handle_token_request(
        self, token: str, scope: Scope, receive: Receive, send: Send
    ) -> None:
        assert self.token_cache is not None
        RATE_LIMIT_REQUESTS.labels(auth="token").inc()
        request_start = time.perf_counter()

        try:
            with RATE_LIMIT_OVERHEAD.labels(auth="token", phase="check").time():
                entry = await self.token_cache.get(token)
        except Exception:
            log.exception("Failed to look up API token")
            API_TOKEN_LOOKUP_ERRORS.inc()
            response = JSONResponse({"error": "could not validate token"}, 503)
            return await response(scope, receive, send)

        if entry is None or not entry.is_valid():
            API_TOKEN_REJECTED.inc()
            response = JSONResponse({"error": "invalid token"}, 401)
            return await response(scope, receive, send)

        # Tokens have no limits for now, we only record their usage
        status_code = 0
        cost = 0

        async def wrapped_send(message: Message) -> None:
            nonlocal status_code, cost
            if message["type"] == "http.response.start":
                tdelta = time.perf_counter() - request_start
                REQUEST_DURATION.labels(auth="token").observe(tdelta)
                status_code = message["status"]
                cost = max([int(tdelta * 100), 1])
            await send(message)

        await self.app(scope, receive, wrapped_send)
        # The response has been sent already, so the client doesn't wait for this
        await self.record_token_usage(entry, scope, status_code, cost)

    async def record_token_usage(
        self, entry: CachedToken, scope: Scope, status_code: int, cost: int
    ) -> None:
        if self.clickhouse_url is None:
            return

        # Use the route template (/measurement/{uid}) rather than the path
        route = scope.get("route")
        row = dict(
            ts=datetime.now(timezone.utc),
            user_id=entry.user_id,
            token_hash_prefix=entry.token_hash[:8],
            method=scope["method"],
            route=route.path if route else "unknown",
            status_code=status_code,
            cost=cost,
        )
        try:
            with RATE_LIMIT_OVERHEAD.labels(auth="token", phase="consume").time():
                await run_in_threadpool(insert_token_usage, self.clickhouse_url, row)
        except Exception:
            log.exception("Failed to record API token usage")
            API_TOKEN_USAGE_ERRORS.inc()
