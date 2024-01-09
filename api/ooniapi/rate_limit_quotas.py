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

import ipaddress
import struct
import time
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


def lm_ipa_to_b(ipaddr: IpAddress) -> bytes:
    return ipaddr.packed


def lm_sec_to_b(v: Union[float, int]) -> bytes:
    return struct.pack("I", int(v * 1000))


def lm_b_to_sec(raw: bytes) -> float:
    return struct.unpack("I", raw)[0] / 1000.0


def lm_b_to_str_ipa(raw_ipa: bytes) -> str:
    if len(raw_ipa) == 4:
        return str(ipaddress.IPv4Address(raw_ipa))
    return str(ipaddress.IPv6Address(raw_ipa))


class LMDB:
    def __init__(self, dbnames: tuple, lmdb_dir: str):
        self._env = lmdb.open(lmdb_dir, metasync=False, max_dbs=10)
        dbnames2 = list(dbnames)
        dbnames2.append("meta")
        self._dbnames = dbnames2
        self._dbs: Dict[str, lmdb._Database] = {}
        for dbname in dbnames2:
            self._dbs[dbname] = self._env.open_db(dbname.encode())

    def purge_databases(self):
        """Used for testing"""
        for dbname in self._dbnames:
            self._dbs[dbname] = self._env.open_db(dbname.encode())
            with self._env.begin(db=self._dbs[dbname], write=True) as txn:
                txn.drop(self._dbs[dbname], delete=False)

    def consume_quota(self, dbname: str, ipa: bytes, used_s: float, limit_s: int):
        db = self._dbs[dbname]
        with self._env.begin(db=db, write=True) as txn:
            raw_val = txn.get(ipa)
            if raw_val is not None:
                v = lm_b_to_sec(raw_val)
            else:
                v = float(limit_s)

            v -= used_s
            if v < 0.0:
                v = 0.0
            txn.put(ipa, lm_sec_to_b(v))

        return v

    def write_tnx(self, dbname="", db=None):
        if dbname:
            db = self._dbs[dbname]
        return self._env.begin(db=db, write=True)


class Limiter:
    def __init__(
        self,
        limits: dict,
        lmdb_dir: str,
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
        self._lmdb = LMDB(dbnames=labels, lmdb_dir=lmdb_dir)
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

        self.increment_quota_counters(1.0)
        self.increment_quota_counters_if_needed()

    def increment_quota_counters(self, tdelta_s: float):
        """Increment quota counters for every tracked ipaddr. When they exceed
        the default value simply delete the key"""
        if tdelta_s <= 0:
            return

        iterable = zip(self._hours, self._ipaddr_limits, self.ipaddr_buckets)
        for hours, limit, db in iterable:
            # limit, vdelta are in seconds
            vdelta_s = tdelta_s * limit / hours / 3600
            with self._lmdb._env.begin(db=db, write=True) as txn:
                i = txn.cursor().iternext()
                for raw_ipa, raw_val in i:
                    v = lm_b_to_sec(raw_val) + vdelta_s
                    if v >= limit:
                        txn.pop(raw_ipa)  # drop from DB: go back to default
                    else:
                        txn.put(raw_ipa, lm_sec_to_b(v))

    def increment_quota_counters_if_needed(self):
        t = time.monotonic()
        tdelta_s = t - self._last_quota_update_time
        if tdelta_s > 3600:
            self.increment_quota_counters(tdelta_s)
            self._last_quota_update_time = t

    def consume_quota(
        self, elapsed_s: float, ipaddr: Optional[IpAddress] = None, token=None
    ) -> float:
        """Consume quota in seconds. Return the lowest remaining value in
        seconds"""
        assert ipaddr or token
        if not ipaddr:
            raise NotImplementedError()

        remaining: float = maxsize
        z = zip(self._ipaddr_limits, self._labels)
        for limit_s, dbname in z:
            ipa = lm_ipa_to_b(ipaddr)
            v = self._lmdb.consume_quota(dbname, ipa, elapsed_s, limit_s)
            if v < remaining:
                remaining = v

        return remaining

    def is_quota_available(self, ipaddr=None, token=None) -> bool:
        """Checks if all quota buckets for an ipaddr/token are > 0"""
        for db in self.ipaddr_buckets:
            with self._lmdb._env.begin(db=db, write=False) as txn:
                raw_val = txn.get(lm_ipa_to_b(ipaddr))
            if raw_val is None:
                continue
            if lm_b_to_sec(raw_val) <= 0:
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

    def get_lowest_daily_quotas_summary(self, n=20) -> List[Tuple[str, float]]:
        """Returns a summary of daily quotas with the lowest values"""
        db = self._lmdb._dbs["ipaddr_per_day"]
        tmp = []
        with self._lmdb._env.begin(db=db, write=False) as txn:
            i = txn.cursor().iternext()
            for raw_ipa, raw_val in i:
                val = lm_b_to_sec(raw_val)
                ipa = lm_b_to_str_ipa(raw_ipa)
                tmp.append((val, ipa))

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
        if self._disabled:  # used in integration tests
            return

        metrics.incr("busy_workers_count")
        self._request_start_time = time.monotonic()

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
            return "429 error", 429

    def _after_request_callback(self, response):
        """Consumes quota and injects HTTP headers when responding to a request"""
        if self._disabled:  # used in integration tests
            return response

        log = current_app.logger
        try:
            tdelta = time.monotonic() - self._request_start_time
            # TODO: implement API call timing metrics
            # timer_path = request.path.split("?", 1)[0]
            # timer_path = "apicall_" + timer_path.replace("/", "__")
            # metrics.timing(timer_path, int(tdelta * 1000))  # ms

            ipaddr = self._get_client_ipaddr()
            if self._limiter.is_ipaddr_whitelisted(ipaddr):
                return response

            if self._limiter.is_page_unmetered(request.path):
                return

            remaining = self._limiter.consume_quota(tdelta, ipaddr=ipaddr)
            response.headers.add("X-RateLimit-Remaining", int(remaining))
            metrics.decr("busy_workers_count")

        except Exception as e:
            log.error(str(e), exc_info=True)

        finally:
            return response

    def __init__(
        self,
        app,
        limits: dict,
        lmdb_dir: str,
        token_check_callback=None,
        ipaddr_methods=["X-Real-Ip", "socket"],
        whitelisted_ipaddrs=None,
        unmetered_pages=None,
    ):
        """"""
        self._limiter = Limiter(
            limits,
            lmdb_dir=lmdb_dir,
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
        self._disabled = False

    def get_lowest_daily_quotas_summary(self, n=20) -> List[Tuple[str, float]]:
        return self._limiter.get_lowest_daily_quotas_summary(n)
