"""
Rate limiter and quota system.

Framework-independent rate limiting mechanism that provides:
    * IP address and token-based accounting
    * customizable quotas based on IP address and token
    * late limiting based on resource usage (time spent on API calls)
    * bucketing based on day, week, month
    * statistics
    * metrics
    * fast in-memory storage

Also provides a connector for Flask

"""

# TODO: add token-based limiting

import time
import ipaddress
from typing import Dict, List, Optional, Tuple, Union, Set
from sys import maxsize

import lmdb  # debdeps: python3-lmdb

from ooniapi.config import metrics

LMDB_DIR = "/var/lib/ooniapi/lmdb"

IpAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
IpAddrBucket = Dict[IpAddress, float]
IpAddrBuckets = Tuple[IpAddrBucket, IpAddrBucket, IpAddrBucket]
TokenBucket = Dict[str, float]
TokenBuckets = Tuple[TokenBucket, TokenBucket, TokenBucket]
StrBytes = Union[bytes, str]


def ipa_lmdb(ipaddr: IpAddress) -> bytes:
    return ipaddr.packed


class LMDB:
    def __init__(self, dbnames: tuple):
        self._env = lmdb.open(LMDB_DIR, metasync=False, max_dbs=10)
        dbnames2 = list(dbnames)
        dbnames2.append("meta")
        self._dbs: Dict[str, lmdb._Database] = {}
        for dbname in dbnames2:
            self._dbs[dbname] = self._env.open_db(dbname.encode())

    def purge_databases(self):
        """Used for testing"""
        raise NotImplementedError
        # self._dbs[dbname] = self._env.open_db(dbname.encode())
        # with self._env.begin(db=self._dbs[dbname], write=True) as txn:
        #    txn.drop(self._dbs[dbname], delete=False)

    def integer_sumupsert(self, dbname: str, key: StrBytes, delta: int, default=0):
        """Sum delta to the value of "key", using a default value if missing
        Return the new value
        """
        db = self._dbs[dbname]
        if isinstance(key, str):
            key2 = key.encode()
        else:
            key2 = key
        with self._env.begin(db=db, write=True) as txn:
            v = int(txn.get(key2, default))
            v += delta
            txn.put(key2, str(v).encode())

        return v

    def write_tnx(self, dbname="", db=None):
        if dbname:
            db = self._dbs[dbname]
        return self._env.begin(db=db, write=True)


class Limiter:
    def __init__(
        self,
        limits: dict,
        token_check_callback=None,
        ipaddr_methods=["X-Real-Ip", "socket"],
        whitelisted_ipaddrs=Optional[List[str]],
        unmetered_pages=Optional[List[str]],
    ):
        # Bucket sequence: month, week, day
        labels = ("ipaddr_per_month", "ipaddr_per_week", "ipaddr_per_day")
        self._hours = [30 * 24, 7 * 24, 1 * 24]
        self._labels = labels
        self._ipaddr_limits = [limits.get(x, None) for x in labels]
        self._token_limits = [limits.get(x, None) for x in labels]
        self._lmdb = LMDB(dbnames=labels)
        self._token_buckets = ({}, {}, {})  # type: TokenBuckets
        self._token_check_callback = token_check_callback
        self._ipaddr_extraction_methods = ipaddr_methods
        self._last_quota_update_time = time.monotonic()
        self._whitelisted_ipaddrs: Set[IpAddress] = set()
        self._unmetered_pages_globs: Set[IpAddress] = set()
        self._unmetered_pages: Set[IpAddress] = set()
        for p in unmetered_pages:
            if p.endswith("*"):
                self._unmetered_pages_globs.add(p.rstrip("*"))
            else:
                self._unmetered_pages.add(p)
        for ipa in whitelisted_ipaddrs or []:
            self._whitelisted_ipaddrs.add(ipaddress.ip_address(ipa))

        self.increment_quota_counters(1)
        self.increment_quota_counters_if_needed()

    def increment_quota_counters(self, tdelta: int):
        """Increment quota counters for every tracked ipaddr. When they exceed
        the default value simply delete the key"""
        if tdelta <= 0:
            return

        # the value is stored as interger in milliseconds
        iterable = zip(self._hours, self._ipaddr_limits, self.ipaddr_buckets)
        for hours, limit, db in iterable:
            vdelta = 1000 * tdelta * limit / hours / 3600
            with self._lmdb._env.begin(db=db, write=True) as txn:
                i = txn.cursor().iternext()
                for raw_ipa, raw_val in i:
                    v = int(raw_val) + vdelta
                    if v >= limit:
                        txn.pop(raw_ipa)
                    else:
                        txn.put(raw_ipa, str(v).encode())

    def increment_quota_counters_if_needed(self):
        t = time.monotonic()
        delta = t - self._last_quota_update_time
        if delta > 3600:
            self.increment_quota_counters(delta)
            self._last_quota_update_time = t

    def consume_quota(
        self, elapsed: float, ipaddr: Optional[IpAddress] = None, token=None
    ) -> float:
        """Consume quota in seconds. Return the lowest remaining value in
        seconds"""
        assert ipaddr or token
        if not ipaddr:
            raise NotImplementedError()

        # TODO handle IPv6?
        assert isinstance(ipaddr, ipaddress.IPv4Address)
        remaining: float = maxsize
        z = zip(self._ipaddr_limits, self._labels)
        for limit, dbname in z:
            ipa = ipa_lmdb(ipaddr)
            elapsed_ms = int(elapsed * 1000)  # milliseconds
            v_ms = self._lmdb.integer_sumupsert(dbname, ipa, -elapsed_ms, default=limit)
            v = v_ms / 1000
            if v < remaining:
                remaining = v

        return remaining

    def is_quota_available(self, ipaddr=None, token=None) -> bool:
        """Checks if all quota buckets for an ipaddr/token are > 0"""
        for db in self.ipaddr_buckets:
            with self._lmdb._env.begin(db=db, write=False) as txn:
                v = float(txn.get(ipa_lmdb(ipaddr), 999))
            if v <= 0:
                return False

        return True

    def is_ipaddr_whitelisted(self, ipaddr: IpAddress) -> bool:
        return ipaddr in self._whitelisted_ipaddrs

    def is_page_unmetered(self, path) -> bool:
        if path in self._unmetered_pages:
            return True
        for u in self._unmetered_pages_globs:
            if path.startswith(u):
                return True

        return False

    def get_lowest_daily_quotas_summary(self, n=20) -> List[Tuple[int, float]]:
        """Returns a summary of daily quotas with the lowest values"""
        db = self._lmdb._dbs["ipaddr_per_day"]
        tmp = []
        with self._lmdb._env.begin(db=db, write=False) as txn:
            i = txn.cursor().iternext()
            for raw_ipa, raw_val in i:
                first_octect = int(raw_ipa[0])
                val = int(raw_val) / 1000.0
                tmp.append((val, first_octect))

        tmp.sort()
        tmp = tmp[:n]
        return [(ipa, val) for val, ipa in tmp]

    @property
    def ipaddr_buckets(self):
        return [self._lmdb._dbs[lab] for lab in self._labels]


# # Flask-specific code # #

from flask import request, current_app
import flask


class FlaskLimiter:
    def _get_client_ipaddr(self) -> IpAddress:
        # https://github.com/alisaifee/flask-limiter/issues/41
        for m in self._limiter._ipaddr_extraction_methods:
            if m == "X-Forwarded-For":
                raise NotImplementedError("X-Forwarded-For ")

            elif m == "X-Real-Ip":
                ipaddr = request.headers.get("X-Real-Ip", None)
                if ipaddr:
                    return ipaddress.ip_address(ipaddr)

            elif m == "socket":
                ipaddr = request.remote_addr
                if ipaddr:
                    return ipaddress.ip_address(ipaddr)

            else:
                raise NotImplementedError(f"IP address method {m} is unknown")

        methods = ",".join(self._limiter._ipaddr_extraction_methods)
        raise Exception(f"Unable to detect IP address using {methods}")

    def _check_limits_callback(self):
        """Check rate limits before processing a request
        Refresh quota counters when needed
        """
        metrics.incr("busy_workers_count")
        self._limiter._lmdb.integer_sumupsert("meta", "busy_workers_count", 1)

        ipaddr = self._get_client_ipaddr()
        if self._limiter.is_ipaddr_whitelisted(ipaddr):
            return

        if self._limiter.is_page_unmetered(request.path):
            return

        self._limiter.increment_quota_counters_if_needed()
        # token = request.headers.get("Token", None)
        # if token:
        # check token validity
        if not self._limiter.is_quota_available(ipaddr=ipaddr):
            flask.abort(429)
        self._request_start_time = time.monotonic()

    def _after_request_callback(self, response):
        """Consume quota and injects HTTP headers when responding to a request"""
        log = current_app.logger
        try:
            ipaddr = self._get_client_ipaddr()
            if self._limiter.is_ipaddr_whitelisted(ipaddr):
                return response

            if self._limiter.is_page_unmetered(request.path):
                return

            assert response
            tdelta = time.monotonic() - self._request_start_time
            remaining = self._limiter.consume_quota(tdelta, ipaddr=ipaddr)
            response.headers.add("X-RateLimit-Remaining", int(remaining))
            metrics.decr("busy_workers_count")
            self._limiter._lmdb.integer_sumupsert("meta", "busy_workers_count", -1)

        except Exception as e:
            log.error(str(e), exc_info=True)

        finally:
            return response

    def __init__(
        self,
        app,
        limits: dict,
        token_check_callback=None,
        ipaddr_methods=["X-Real-Ip", "socket"],
        whitelisted_ipaddrs=None,
        unmetered_pages=None,
    ):
        """"""
        self._limiter = Limiter(
            limits,
            token_check_callback=token_check_callback,
            ipaddr_methods=ipaddr_methods,
            whitelisted_ipaddrs=whitelisted_ipaddrs,
            unmetered_pages=unmetered_pages,
        )
        if app.extensions.get("limiter"):
            raise Exception("The Flask app already has an extension named 'limiter'")

        app.before_request(self._check_limits_callback)
        app.after_request(self._after_request_callback)
        app.extensions["limiter"] = self

    def get_lowest_daily_quotas_summary(self, n=20) -> List[Tuple[int, float]]:
        return self._limiter.get_lowest_daily_quotas_summary(n)
