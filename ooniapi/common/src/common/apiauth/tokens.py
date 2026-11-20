import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .models import ApiToken

log = logging.getLogger(__name__)

TOKEN_PREFIX = "ooni_"


def hash_token(token: str) -> str:
    # Must match the hashing done by ooniapi/common/scripts/apitoken.py
    return hashlib.sha256(token.encode()).hexdigest()


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
            postgresql_url, pool_pre_ping=True, connect_args={"connect_timeout": 2}
        )
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, CachedToken] = {}

    def _fetch(self, token_hash: str) -> Optional[ApiToken]:
        with Session(self.engine) as session:
            return session.get(ApiToken, token_hash)

    async def get(self, token: str) -> Optional[CachedToken]:
        """
        Returns the token if it exists, None otherwise.
        Remember to check for the expiration date.

        Raises if the database can't be reached and the token is not cached
        """
        token_hash = hash_token(token)
        entry = self._cache.get(token_hash)
        if entry is not None and time.monotonic() - entry.fetched_at < self.ttl_seconds:
            return entry

        try:
            row = await run_in_threadpool(self._fetch, token_hash)
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
