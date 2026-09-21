# ooniapi end-to-end test harness

Deploys the ooniapi backend services with docker-compose and exercises them
with a real, containerized [miniooni](https://github.com/ooni/probe-cli/tree/master/internal/cmd/miniooni)
client, closing the loop on the question raised in
[ooni/backend#1145](https://github.com/ooni/backend/pull/1145): *"was this
tested with a real client?"*.

## What this actually tests

1. **Real submission** - runs the `example` experiment (a synthetic,
   network-independent experiment built into probe-cli) through an actual
   compiled `miniooni` binary, pointed at the compose stack via
   `--probe-services`. This exercises session bootstrap, `ooniprobe`'s
   `/api/v1/submit_measurement`, and the handoff to `fastpath`.
2. **Retrieval** - polls `oonimeasurements`'s `/api/v1/measurement_meta`
   until the submitted measurement is servable, proving the full
   submit → fastpath → ClickHouse → retrieval pipeline works.

This deliberately does **not** include a `/api/v1/check-in` probe_cc
validation check. That's a regression test for
[ooni/backend#1145](https://github.com/ooni/backend/pull/1145) (a
malformed `probe_cc` should return 422, not crash the service with a 500
per issue #1144) and would fail against master until that PR merges. Adding
it here would mean this harness can't merge with green checks, so it's
being added directly in #1145 instead - see `scripts/run-checks.sh`'s
top-of-file comment for the same note in context.

## Architecture

```
                        ┌──────────────┐
   miniooni  ───────────▶   router     │  nginx, replicates the ALB
  (probe-cli)           │  (nginx)     │  path-routing rules from
                        └──────┬───────┘  ooni/devops/tf/modules/ooniapi_frontend
           ┌───────┬───────────┼───────────┬─────────┬───────────┐
           ▼       ▼           ▼           ▼         ▼           ▼
       ooniauth oonirun   ooniprobe  oonifindings oonimeasurements testlists
                              │                          ▲
                              ▼                          │
                          fastpath ─────────────────────>│ (via ClickHouse)
                              │
                              ▼
                          clickhouse-server        postgres (shared schema,
                                                    migrated once by `migrate`)
```

The `router` service is a **new** nginx config
(`nginx/router.conf`), not the `ooniapi/services/reverseproxy` image - that
one just forwards everything to a single upstream, because in production
path-based routing already happened at the AWS ALB. Locally we have several
independent containers instead of ALB target groups, so `router.conf`
re-implements the same path → service mapping found in
`ooni/devops/tf/modules/ooniapi_frontend/main.tf`. **If that file changes
upstream, `nginx/router.conf` needs to be updated to match** - there is no
automated link between the two repos.

## Running it

```sh
cd ooniapi/tests/e2e
cp .env.example .env   # optional, defaults are fine
./scripts/run.sh
```

This builds the six service images (via each service's own
`make docker-build` - see comments in `scripts/build-images.sh` for why),
builds miniooni from `PROBE_CLI_REF` (default: `master`) - including the
real anonymous-credentials staticlib via probe-cli's own `make userauth`,
built from source by default (`USERAUTH_MODE=source`; see
`miniooni/Dockerfile` and the "Known gaps" note below) - brings the stack
up, runs the checks, prints logs on failure, and tears everything down.

Useful env vars (see `.env.example`):
- `PROBE_CLI_REF` - test against a specific probe-cli tag/branch/commit.
- `USERAUTH_MODE` - `source` (default) or `prebuilt`; see `miniooni/Dockerfile`.
- `SKIP_BUILD=1` - skip rebuilding the ooniapi service images.
- `KEEP_UP=1` - leave the stack running after the run for manual poking.

To leave the stack up and experiment by hand:

```sh
KEEP_UP=1 SKIP_BUILD=1 ./scripts/run.sh
docker compose --profile client run --rm miniooni webconnectivity \
    --probe-services http://localhost:8080 -i https://example.org --yes
curl http://localhost:8080/api/v1/measurement_meta?report_id=...
docker compose down -v
```

## Known gaps / deliberate scope decisions

- **Geolocation is real, not mocked.** `miniooni` looks up the probe's
  public IP/ASN/country via real external services (Cloudflare, STUN,
  Ubuntu's geoip service) before it ever talks to `--probe-services`. This
  is not configurable without patching probe-cli, so this harness needs
  real internet egress (fine on GitHub Actions runners by default) even
  though the *backend* calls are fully local.
- **Anonymous credentials are not exercised end-to-end.** The `miniooni`
  image builds the *real* `internal/userauth` staticlib (a Rust crate),
  built from source by default rather than trusting a prebuilt binary
  blob - see `miniooni/Dockerfile` for the `USERAUTH_MODE` build arg. CI
  (`.github/workflows/test_e2e_miniooni.yml`) runs *both*
  `USERAUTH_MODE=source` and `USERAUTH_MODE=prebuilt` in its matrix, since
  a regression in either path is otherwise easy to miss - which is exactly
  what happened upstream: probe-cli's `userauthVersion` was bumped without
  updating the from-source path's pinned SHA256, so `USERAUTH_MODE=source`
  builds fail against probe-cli master until that's fixed there (a patch
  has been sent upstream, but this harness doesn't wait on it landing -
  the `source` matrix job going red *is* the harness doing its job). This
  gives miniooni's client fully capable of the credentialed submission
  flow either way. What's still missing is the *server* side: ooniprobe's
  `/api/v1/manifest` endpoint needs a real S3 bucket
  (`ANONC_MANIFEST_BUCKET`/`ANONC_MANIFEST_FILE`), which we leave
  unconfigured. probe-cli's submitter (`engine.Session.NewSubmitter`)
  gracefully falls back to plain (non-credentialed) submission when the
  manifest fetch fails, so the core pipeline test still passes either way.
  Standing up a local S3-compatible service (e.g. MinIO) to test the
  credentialed path end-to-end is a reasonable follow-up but out of scope
  here.
- **Tor targets / Psiphon config / `ooniauth` email sending** are similarly
  unconfigured (all need real S3 or SES). `ooniauth` is deployed and health
  checked but its register/login flows aren't exercised by
  `scripts/run-checks.sh`.
- **Only the `example` experiment is run.** It's `InputNone` (no real
  network target, ~1s runtime), chosen deliberately so the test doesn't
  depend on real-world network conditions, test helpers, or citizenlab
  test-list data. It also means `/api/v1/check-in` isn't exercised at all
  by this harness (`InputNone` experiments never call it - see the note
  above about where check-in coverage lives instead). Extending this to
  run `webconnectivity`/`dnscheck` against real targets (and therefore also
  hitting `check-in`'s target-selection logic end-to-end via the client) is
  a natural next step but needs real test-helper infrastructure or a
  mocked one.

## Extending the client-version matrix

`aagbsn`'s comment on #1145 asked for testing "against a matrix of client
versions". The `.github/workflows/test_e2e_miniooni.yml` workflow does this
by building `miniooni` from a `strategy.matrix` of `PROBE_CLI_REF` values
(build args plumbed through `docker-compose.yml`'s `miniooni` service).
Add more refs to that matrix as needed.
