"""
Load generator for the thread-pool starvation test (see README.md).

Runs probes ("victims": requests without a token, as ordinary users send) and,
optionally, an attack of requests with made-up `ooni_` tokens, then injects a
Postgres fault part way through and reports victim latency before, during and
after the fault.

Victims (each from a new random X-Forwarded-For, so the IP quota never applies):
  async  GET /                          async endpoint, no worker thread
  thread GET /api/_/check_report_id      sync endpoint, one worker thread
  click  GET /api/v1/measurements?limit=1  ClickHouse query on a worker thread
  token  GET /api/_/check_report_id      with a valid token not seen before, so
                                         it's looked up in Postgres every time
"""

import argparse
import asyncio
import json
import random
import secrets
import statistics
import subprocess
import time

import httpx

BASE = "http://127.0.0.1:8000"
VICTIMS = {
    "async": "/",
    "thread": "/api/_/check_report_id",
    "click": "/api/v1/measurements?limit=1",
    "token": "/api/_/check_report_id",
}
FAULTS = {
    "none": ("true", "true"),
    # A hung server: the kernel still accepts connections and ACKs, nothing answers
    "stop": ("pkill -STOP -u postgres", "pkill -CONT -u postgres"),
    # A network partition: packets to and from Postgres are dropped
    "drop": (
        "iptables -I INPUT -i lo -p tcp --dport 5432 -j DROP && "
        "iptables -I INPUT -i lo -p tcp --sport 5432 -j DROP",
        "iptables -D INPUT -i lo -p tcp --dport 5432 -j DROP && "
        "iptables -D INPUT -i lo -p tcp --sport 5432 -j DROP",
    ),
}


def rand_ip(prefix="198.18"):
    return f"{prefix}.{random.randint(0, 255)}.{random.randint(1, 254)}"


class Recorder:
    def __init__(self):
        self.t0 = time.monotonic()
        self.events = []  # (kind, t_start, latency or None, status)

    def add(self, kind, start, latency, status):
        self.events.append((kind, start - self.t0, latency, status))


async def one(client, rec, kind, path, headers, timeout):
    start = time.monotonic()
    try:
        r = await client.get(BASE + path, headers=headers, timeout=timeout)
        rec.add(kind, start, time.monotonic() - start, r.status_code)
    except httpx.TimeoutException:
        rec.add(kind, start, None, "timeout")
    except httpx.HTTPError as e:
        rec.add(kind, start, None, type(e).__name__)


TOKENS_SEEDED = 2000  # ooni_valid_0 .. ooni_valid_1999, see inner.sh
_next_token = iter(range(TOKENS_SEEDED))


async def victim_loop(client, rec, kind, path, rate, stop):
    tasks = []
    while not stop.is_set():
        h = {"X-Forwarded-For": rand_ip()}
        if kind == "token":
            h["Authorization"] = f"Bearer ooni_valid_{next(_next_token)}"
        tasks.append(asyncio.create_task(one(client, rec, "victim:" + kind, path, h, 10)))
        await asyncio.sleep(1 / rate)
    await asyncio.gather(*tasks)


async def attack_worker(client, rec, ip_mode, token, stop):
    while not stop.is_set():
        ip = "203.0.113.7" if ip_mode == "single" else rand_ip("100.64")
        h = {"X-Forwarded-For": ip}
        if token == "random":
            h["Authorization"] = "Bearer ooni_" + secrets.token_hex(16)
        elif token == "valid":
            # One valid token, as a client sending requests in parallel
            h["Authorization"] = "Bearer ooni_valid"
        await one(client, rec, "attack", VICTIMS["thread"], h, 30)


async def health_loop(client, rec, every, stop):
    tasks = []
    while not stop.is_set():
        # 5 s, as an ALB health check's default timeout
        tasks.append(asyncio.create_task(one(client, rec, "health", "/health", {}, 5)))
        await asyncio.sleep(every)
    await asyncio.gather(*tasks)


async def thread_sampler(pid, rec, stop, out):
    while not stop.is_set():
        try:
            with open(f"/proc/{pid}/status") as f:
                n = int(next(l for l in f if l.startswith("Threads:")).split()[1])
            out.append((time.monotonic() - rec.t0, n))
        except Exception:
            pass
        await asyncio.sleep(0.5)


def pct(vals, p):
    if not vals:
        return None
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(p / 100 * len(vals)))]


def summarize(rec, windows, threads):
    report = {}
    for name, (a, b) in windows.items():
        w = {}
        for kind in sorted({e[0] for e in rec.events}):
            evs = [e for e in rec.events if e[0] == kind and a <= e[1] < b]
            if not evs:
                continue
            lat = [e[2] for e in evs if e[2] is not None]
            statuses = {}
            for e in evs:
                statuses[str(e[3])] = statuses.get(str(e[3]), 0) + 1
            w[kind] = {
                "n": len(evs),
                "p50": round(pct(lat, 50), 3) if lat else None,
                "p95": round(pct(lat, 95), 3) if lat else None,
                "max": round(max(lat), 3) if lat else None,
                "status": statuses,
            }
        th = [n for t, n in threads if a <= t < b]
        w["threads_max"] = max(th) if th else None
        report[name] = w
    return report


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, required=True, help="uvicorn's pid")
    ap.add_argument("--fault", choices=FAULTS, default="none")
    ap.add_argument("--attack", type=int, default=0, help="concurrent attackers")
    ap.add_argument("--attack-ip", choices=["single", "spoof"], default="single")
    ap.add_argument("--attack-token", choices=["random", "none", "valid"], default="random")
    ap.add_argument("--health-every", type=float, default=0)
    ap.add_argument("--victim-rate", type=float, default=4, help="per victim kind, req/s")
    ap.add_argument("--warm", type=float, default=5, help="seconds before the fault")
    ap.add_argument("--fault-for", type=float, default=30)
    ap.add_argument("--recover", type=float, default=15)
    a = ap.parse_args()

    rec = Recorder()
    threads = []
    stop_all, stop_attack = asyncio.Event(), asyncio.Event()
    limits = httpx.Limits(max_connections=2000, max_keepalive_connections=2000)
    async with httpx.AsyncClient(limits=limits) as client:
        bg = [asyncio.create_task(thread_sampler(a.pid, rec, stop_all, threads))]
        for kind, path in VICTIMS.items():
            bg.append(asyncio.create_task(
                victim_loop(client, rec, kind, path, a.victim_rate, stop_all)))
        if a.health_every:
            bg.append(asyncio.create_task(health_loop(client, rec, a.health_every, stop_all)))
        attackers = [asyncio.create_task(attack_worker(client, rec, a.attack_ip, a.attack_token, stop_attack))
                     for _ in range(a.attack)]

        await asyncio.sleep(a.warm)
        t_fault = time.monotonic() - rec.t0
        subprocess.run(FAULTS[a.fault][0], shell=True, check=True)
        await asyncio.sleep(a.fault_for)
        t_heal = time.monotonic() - rec.t0
        # The attack stops with the fault, so "after" shows recovery alone
        stop_attack.set()
        subprocess.run(FAULTS[a.fault][1], shell=True, check=True)
        await asyncio.sleep(a.recover)
        t_end = time.monotonic() - rec.t0
        stop_all.set()
        # Let in-flight requests finish (or time out) so they're counted
        await asyncio.wait_for(asyncio.gather(*bg, *attackers), 60)

    windows = {
        "before": (0, t_fault),
        "fault": (t_fault, t_heal),
        "after": (t_heal, t_end),
    }
    print(json.dumps({"args": vars(a), "windows": summarize(rec, windows, threads)}))


asyncio.run(main())
