# Thread-pool load test for API token lookups

Checks whether API token lookups in Postgres can starve the worker threads
that the endpoints and their ClickHouse queries share (anyio's default
limiter: 40 threads per process). It runs the service against real Postgres
and ClickHouse in one container, sends ordinary requests and, optionally, a
flood of requests with tokens, and freezes or cuts off Postgres part way
through.

`tests/test_token_threads.py` covers the same behaviour in the normal test
suite, without databases.

## Running it

Needs podman: the ClickHouse binary comes from an image mount of
`clickhouse/clickhouse-server:25.8.29.51`. The test image is built once
(tagged by a hash of `Containerfile` and `pyproject.toml`) and kept; the
container is removed afterwards.

    # all scenarios, against this checkout (~10 minutes)
    tests/threadpool/run.sh results.jsonl
    # some scenarios, against another checkout's ooniapi directory
    SCENARIOS="baseline flood-stop" tests/threadpool/run.sh ../other/ooniapi results.jsonl

`run.sh` prints one line per scenario window; `summarize.py results.jsonl`
prints them again.

## What it does

`inner.sh` starts, in the container:

- Postgres 15 on 127.0.0.1, with the `apitoken` table and 2,001 valid tokens
- ClickHouse with `common/fixtures/initdb/01-scheme.sql`
- the service with uvicorn (one process, as in the Dockerfile) and prod's
  rate limits (`4000/hour;400000/day;200000/7day`, `/health` unmetered)

`load.py` then runs each scenario against a fresh process:

- **Probes**, 4 requests/s each, each from a new address so the IP quota
  never applies:
  - `async`: `GET /`, an async endpoint that needs no worker thread
  - `thread`: `GET /api/_/check_report_id`, a sync endpoint (one worker thread)
  - `click`: `GET /api/v1/measurements?limit=1`, a ClickHouse query on a worker thread
  - `token`: like `thread`, with a valid token not used before, so it's looked up
- **Attackers** (optional): N clients sending requests in a loop, with made-up
  `ooni_` tokens (`random`), no token (`none`) or one valid token (`valid`),
  from one address (`single`) or a new one each time (`spoof`; the
  middleware takes the first `X-Forwarded-For` entry)
- **The fault**, 5 s in, for 30 s, then 15 s to recover:
  - `stop`: `SIGSTOP` to Postgres, as a hung server: connections are accepted
    and data is ACKed, but nothing answers
  - `drop`: iptables drops Postgres's packets, as a network partition

Each window reports, per kind, the request count, p50/p95/max latency (s),
the status codes (`timeout` = no answer in 10 s; 30 s for attackers) and the
most threads the process had.

| Scenario | Attackers | Fault |
|---|---|---|
| `baseline` | none | none |
| `health-stop`, `health-drop` | none, `/health` every 2 s | stop, drop |
| `valid-burst` | 30, one valid token, cache cold | none |
| `flood-ok` | 200, made-up tokens, spoofed | none |
| `flood-1ip-stop` | 200, made-up tokens, one address | stop |
| `flood-notoken` | 200, no token, spoofed | stop |
| `flood-stop-10`, `-40`, `flood-stop` | 10, 40, 200, made-up tokens, spoofed | stop |
| `flood-drop` | 200, made-up tokens, spoofed | drop |

## Reading the results

Starvation shows as `thread`, `click` and `token` probes slowing down or
timing out while `async` stays fast: the event loop is free, the threads
aren't. When all four slow down together, the process is short of CPU
instead, as with any flood of that size (compare `flood-notoken`).
