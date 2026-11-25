import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

import anyio
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .models import ApiToken

log = logging.getLogger(__name__)

TOKEN_PREFIX = "ooni_"

# Postgres keepalive and TCP settings: a connection whose packets go
# unacknowledged (the database host or the network is gone) fails within
# seconds instead of the kernel's ~15 minutes of retransmissions
PG_TCP_ARGS = {
    "keepalives": 1,
    "keepalives_idle": 5,
    "keepalives_interval": 2,
    "keepalives_count": 2,
    "tcp_user_timeout": 5000,  # milliseconds
}


class ThreadBudget:
    """
    Runs blocking calls on at most `size` threads of their own, apart from the
    worker threads that the endpoints and their ClickHouse queries share (40
    by default), so a slow or hung database can't stall the rest of the API.

    Calls wait for a free thread, and raise TimeoutError if they're still
    waiting after `timeout` seconds. A call that's running isn't interrupted:
    its caller gets the result when it returns, and it keeps its thread, so
    stuck calls never take more than `size` threads. The database's own
    timeouts (connect, pool, TCP) bound how long most calls run.
    """

    def __init__(self, size: int, timeout: float):
        self.size = size
        self.timeout = timeout
        self._limiter: Optional[anyio.CapacityLimiter] = None

    async def run(self, func, *args):
        if self._limiter is None:  # created inside the event loop
            self._limiter = anyio.CapacityLimiter(self.size)
        with anyio.fail_after(self.timeout):
            return await anyio.to_thread.run_sync(func, *args, limiter=self._limiter)


def hash_token(token: str) -> str:
    # Must match the hashing done by ooniapi/common/scripts/apitoken.py
    return hashlib.sha256(token.encode()).hexdigest()


# Token lookups have up to LOOKUP_THREADS threads. One still waiting for a
# thread after LOOKUP_TIMEOUT seconds fails: the request gets a 503, or the
# cached entry if there is one
LOOKUP_THREADS = 4
LOOKUP_TIMEOUT = 3


@dataclass
class CachedToken:
    token_hash: str
    user_id: str
    expires_at: Optional[datetime]
    fetched_at: float  # time.monotonic()

    def is_valid(self) -> bool:
        return self.expires_at is None or self.expires_at > datetime.now(timezone.utc)


class ApiTokenCache:
    """
    In-memory cache of API tokens, used for authentication only. Quotas are
    a separate concern and are counted in valkey by the rate limiter.

    Tokens are looked up in postgres when missing or older than
    `ttl_seconds`, so revocations are picked up after at most `ttl_seconds`.
    """

    def __init__(self, postgresql_url: str, ttl_seconds: int = 60):
        # Creates engine once, is reused for many requests. 
        # The timeout keeps an unreachable database from blocking threadpool 
        # workers.
        # pool_pre_ping replaces dead connections
        self.engine = create_engine(
            postgresql_url,
            pool_pre_ping=True,
            # Seconds to wait for a free connection when the pool is exhausted
            pool_timeout=2,
            connect_args={
                "connect_timeout": 2,
                # Milliseconds, enforced by postgres on every query
                "options": "-c statement_timeout=2000",
                **PG_TCP_ARGS,
            },
        )
        self._threads = ThreadBudget(LOOKUP_THREADS, LOOKUP_TIMEOUT)
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, CachedToken] = {}

    def _fetch(self, token_hash: str) -> Optional[ApiToken]:
        with Session(self.engine) as session:
            return session.get(ApiToken, token_hash)

    def get_cached(self, token: str) -> Optional[CachedToken]:
        """
        Returns the token if it's cached and fresh, without querying the database
        """
        entry = self._cache.get(hash_token(token))
        if entry is not None and time.monotonic() - entry.fetched_at < self.ttl_seconds:
            return entry
        return None

    async def get(self, token: str) -> Optional[CachedToken]:
        """
        Returns the token if it exists, None otherwise.
        Remember to check for the expiration date.

        Raises if the database can't be reached and the token is not cached
        """
        cached = self.get_cached(token)
        if cached is not None:
            return cached

        token_hash = hash_token(token)
        # Possibly stale, used if the database can't be reached
        entry = self._cache.get(token_hash)
        try:
            row = await self._threads.run(self._fetch, token_hash)
        except Exception:
            if entry is None:
                raise
            log.exception("Failed to refresh API token, using cached value")
            return entry

        if row is None:
            self._cache.pop(token_hash, None)
            return None

        entry = CachedToken(
            token_hash=token_hash,
            user_id=row.user_id,
            expires_at=row.expires_at,
            fetched_at=time.monotonic(),
        )
        self._cache[token_hash] = entry
        return entry
