import ipaddress
import time
from sys import maxsize
from typing import Dict, List, Optional, Set, Tuple, Union

import redis
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REDIS_URL = "redis://localhost:6379/0"
REDIS_KEY_PREFIX = "ooniapi:ratelimit:"


def ipa_to_key(label: str, ipaddr: str) -> str:
    """Convert IP address to Redis key"""
    return f"{REDIS_KEY_PREFIX}{label}:{ipaddr}"


def key_to_ipa(key: str) -> str:
    """Extract IP address string from Redis key"""
    # Key format: ooniapi:ratelimit:<label>:<ipaddr>
    return key.rsplit(":", 1)[-1]


class RedisStore:
    def __init__(self, dbnames: tuple, redis_url: str = REDIS_URL):
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._dbnames = list(dbnames)

    def purge_databases(self):
        """Used for testing"""
        for dbname in self._dbnames:
            pattern = f"{REDIS_KEY_PREFIX}{dbname}:*"
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match=pattern, count=1000)
                if keys:
                    self._redis.delete(*keys)
                if cursor == 0:
                    break

    def consume_quota(
        self, dbname: str, ipaddr: str, used_s: float, limit_s: int
    ) -> float:
        """Atomically consume quota and return remaining value"""
        key = ipa_to_key(dbname, ipaddr)

        # Use a Lua script for atomic read-modify-write
        lua_script = """
        local key = KEYS[1]
        local used_s = tonumber(ARGV[1])
        local limit_s = tonumber(ARGV[2])

        local v = redis.call('GET', key)
        if v == false then
            v = limit_s
        else
            v = tonumber(v)
        end

        v = v - used_s
        if v < 0 then
            v = 0
        end

        redis.call('SET', key, v)
        return tostring(v)
        """
        result = self._redis.eval(lua_script, 1, key, used_s, limit_s)
        return float(result)

    def get_value(self, dbname: str, ipaddr: str) -> Optional[float]:
        """Get current quota value for an IP address"""
        key = ipa_to_key(dbname, ipaddr)
        val = self._redis.get(key)
        if val is None:
            return None
        return float(val)

    def set_value(self, dbname: str, ipaddr: str, value: float):
        """Set quota value for an IP address"""
        key = ipa_to_key(dbname, ipaddr)
        self._redis.set(key, value)

    def delete_key(self, dbname: str, ipaddr: str):
        """Delete a key (reset to default)"""
        key = ipa_to_key(dbname, ipaddr)
        self._redis.delete(key)

    def scan_keys(self, dbname: str):
        """Iterate over all keys for a given bucket"""
        pattern = f"{REDIS_KEY_PREFIX}{dbname}:*"
        cursor = 0
        while True:
            cursor, keys = self._redis.scan(cursor, match=pattern, count=1000)
            for key in keys:
                yield key
            if cursor == 0:
                break

    def increment_all_quotas(self, dbname: str, vdelta_s: float, limit_s: float):
        """Increment quota counters for all tracked IPs in a bucket.
        When they exceed the limit, delete the key (reset to default)."""
        lua_script = """
        local key = KEYS[1]
        local vdelta_s = tonumber(ARGV[1])
        local limit_s = tonumber(ARGV[2])

        local v = redis.call('GET', key)
        if v == false then
            return 0
        end

        v = tonumber(v) + vdelta_s
        if v >= limit_s then
            redis.call('DEL', key)
            return 1
        else
            redis.call('SET', key, v)
            return 0
        end
        """
        for key in self.scan_keys(dbname):
            self._redis.eval(lua_script, 1, key, vdelta_s, limit_s)


class Limiter:
    def __init__(
        self,
        limits: dict,
        redis_url: str = REDIS_URL,
    ):
        # Bucket sequence: month, week, day
        labels = ("ipaddr_per_month", "ipaddr_per_week", "ipaddr_per_day")
        self._hours = [30 * 24, 7 * 24, 1 * 24]
        self._labels = labels
        self._ipaddr_limits = [limits.get(x, 0.0) for x in labels]
        self._store = RedisStore(dbnames=labels, redis_url=redis_url)
        self._last_quota_update_time = time.monotonic()

        self.increment_quota_counters(1.0)
        self.increment_quota_counters_if_needed()

    def increment_quota_counters(self, tdelta_s: float):
        """Increment quota counters for every tracked ipaddr. When they exceed
        the default value simply delete the key"""
        if tdelta_s <= 0:
            return

        iterable = zip(self._hours, self._ipaddr_limits, self._labels)
        for hours, limit, label in iterable:
            # limit, vdelta are in seconds
            vdelta_s = tdelta_s * limit / hours / 3600
            self._store.increment_all_quotas(label, vdelta_s, limit)

    def increment_quota_counters_if_needed(self):
        t = time.monotonic()
        tdelta_s = t - self._last_quota_update_time
        if tdelta_s > 3600:
            self.increment_quota_counters(tdelta_s)
            self._last_quota_update_time = t

    def consume_quota(self, elapsed_s: float, ipaddr: str) -> float:
        """Consume quota in seconds. Return the lowest remaining value in
        seconds"""
        remaining: float = maxsize
        z = zip(self._ipaddr_limits, self._labels)
        for limit_s, dbname in z:
            v = self._store.consume_quota(dbname, ipaddr, elapsed_s, limit_s)
            if v < remaining:
                remaining = v

        return remaining

    def is_quota_available(self, ipaddr) -> bool:
        """Checks if all quota buckets for an ipaddr/token are > 0"""
        for label in self._labels:
            val = self._store.get_value(label, ipaddr)
            if val is None:
                continue
            if val <= 0:
                return False

        return True

    def get_lowest_daily_quotas_summary(self, n=20) -> List[Tuple[str, float]]:
        """Returns a summary of daily quotas with the lowest values"""
        tmp = []
        for key in self._store.scan_keys("ipaddr_per_day"):
            val = self._store._redis.get(key)
            if val is not None:
                ipa = key_to_ipa(key)
                tmp.append((float(val), ipa))

        tmp.sort()
        tmp = tmp[:n]
        return [(ipa, val) for val, ipa in tmp]


class RateLimiterMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        redis_url: str,
        whitelisted_ipaddrs: Optional[List[str]] = None,
        unmetered_pages: Optional[List[str]] = None,
        quotatest_pages: Optional[List[str]] = None,
    ):
        limits = dict(
            ipaddr_per_month=60000,
            ipaddr_per_week=20000,
            ipaddr_per_day=4000,
        )
        self.app = app
        self.unmetered_pages = unmetered_pages
        self.whitelisted_ipaddrs = whitelisted_ipaddrs
        self.quotatest_pages = quotatest_pages
        self.limiter = Limiter(limits=limits, redis_url=redis_url)

    def get_client_ipaddr(self, scope: Scope, receive: Receive) -> str:
        request = Request(scope, receive)

        headers = Headers(scope=scope)
        x_forwarded_for = headers.get("X-Forwarded-For")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        return request.client.host

    def is_unmetered_page(self, path: str) -> bool:
        if self.unmetered_pages is None:
            return False

        return path in self.unmetered_pages

    def is_ip_whitelisted(self, ipaddr: str) -> bool:
        if self.whitelisted_ipaddrs is None:
            return False

        return ipaddr in self.whitelisted_ipaddrs

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

        self.limiter.increment_quota_counters_if_needed()
        if not self.limiter.is_quota_available(ipaddr=ipaddr):
            response = PlainTextResponse("Quota exceeded", 429)
            return await response(scope, receive, send)

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                tdelta = time.perf_counter() - request_start
                if scope["path"] in self.quotatest_pages:
                    tdelta = 42
                remaining = self.limiter.consume_quota(tdelta, ipaddr=ipaddr)
                headers = MutableHeaders(scope=message)
                headers.append("X-RateLimit-Remaining", str(int(remaining)))
            await send(message)

        await self.app(scope, receive, wrapped_send)
