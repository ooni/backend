import hashlib
import time
from typing import List

from limits import parse_many as parse_many_limits
from limits.aio.storage import RedisStorage
from limits.aio.strategies import MovingWindowRateLimiter
from prometheus_client import Counter, Histogram
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

## We convert the previous limits by multiplying by 100, since they were previously expressed as seconds of runtime per period. Now we are expressing cost as the number of 10ms.
# ipaddr_per_month=60000,
# ipaddr_per_week=20000,
# ipaddr_per_day=4000,

DEFAULT_LIMITS = "10/minute;400000/day;200000/7day"

## Metrics
RATE_LIMIT_HITS = Counter(
    "rate_limit_hits",
    "The number of requests that triggered a rate limit",
)

REQUEST_DURATION = Histogram(
    "rate_limit_request_duration",
    "The duration of requests not triggered by a rate limit",
)


def hash_ipaddr(ipaddr: str, key: str) -> str:
    return hashlib.blake2b(
        ipaddr.encode(), key=key.encode("utf-8"), digest_size=8
    ).hexdigest()


class RateLimiterMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        valkey_url: str,
        hashing_key: str = "CHANGEME",
        rate_limits: str = DEFAULT_LIMITS,
        whitelisted_ipaddrs: List[str] = [],
        unmetered_pages: List[str] = [],
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
        self.limits_storage = RedisStorage(f"async+{valkey_url}")
        self.limiter = MovingWindowRateLimiter(self.limits_storage)
        self.rate_limits = parse_many_limits(rate_limits)
        self.hashing_key = hashing_key

    def get_client_ipaddr(self, scope: Scope, receive: Receive) -> str:
        request = Request(scope, receive)

        headers = Headers(scope=scope)
        x_forwarded_for = headers.get("X-Forwarded-For")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        return request.client.host

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

        request_start = time.perf_counter()

        hashed_ipaddr = hash_ipaddr(ipaddr, self.hashing_key)
        remaining = await self.get_min_available_quota(hashed_ipaddr)
        if remaining <= 0:
            RATE_LIMIT_HITS.inc()
            response = PlainTextResponse("Quota exceeded", 429)
            headers = MutableHeaders(scope=scope)
            headers.append("X-RateLimit-Remaining", "0")
            return await response(scope, receive, send)

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                tdelta = time.perf_counter() - request_start
                REQUEST_DURATION.observe(tdelta)
                # Cost is calculated by assuming 10ms of request time is 1 unit
                # rounded to 1 when it's less than 10ms
                cost = max([int(tdelta * 100), 1])
                await self.consume_rate_limits(hashed_ipaddr, cost=cost)
                headers = MutableHeaders(scope=message)
                headers.append("X-RateLimit-Remaining", str(max([remaining - cost, 0])))
            await send(message)

        await self.app(scope, receive, wrapped_send)
