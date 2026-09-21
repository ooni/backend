# ooniapi end-to-end test harness

Deploys the ooniapi backend services with docker-compose and exercises them
with a real, containerized [miniooni](https://github.com/ooni/probe-cli/tree/master/internal/cmd/miniooni)
client, closing the loop on the question raised in
[ooni/backend#1145](https://github.com/ooni/backend/pull/1145): *"was this
tested with a real client?"*.

## What this actually tests

1. **Real submission, with real anonymous credentials** - runs the
   `example` experiment (a synthetic, network-independent experiment built
   into probe-cli) through an actual compiled `miniooni` binary, pointed
   at the compose stack via `--probe-services`. This exercises session
   bootstrap, `ooniprobe`'s `/api/v1/submit_measurement`, the handoff to
   `fastpath` - and, since miniooni attempts credentialed submission by
   default, also `GET /api/v1/manifest` and `POST /api/v1/sign_credential`
   against a real manifest served from MinIO (see "Architecture" and
   `docker-compose.yml`'s `minio`/`minio-init` services).
2. **Anonymous-credentials verification** - checks miniooni's own log for
   evidence it didn't silently fall back to uncredentialed submission,
   then confirms server-side (via `verification_status` in
   `oonimeasurements`'s response) that the ZKP proof actually verified -
   see `scripts/run-checks.sh` step 2/3.
3. **Retrieval** - polls `oonimeasurements`'s `/api/v1/measurement_meta`
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
                              │  │                       ▲
                              │  ▼                        │
                              │ minio (manifest.json)     │
                              ▼                           │
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
# --probe-services needs router's literal container IP, not a hostname -
# see scripts/run-checks.sh's comment above this same command for why.
ROUTER_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$(docker compose ps -q router)")"
docker compose --profile client run --rm miniooni webconnectivity \
    --probe-services "http://${ROUTER_IP}" -i https://example.org --yes
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
- **Anonymous credentials ARE now exercised end-to-end** - client and
  server both. `miniooni` builds the *real* `internal/userauth` staticlib
  (a Rust crate), from source by default rather than trusting a prebuilt
  binary blob (`USERAUTH_MODE` build arg; CI runs both `source` and
  `prebuilt` - see `miniooni/Dockerfile`). Server-side, `docker-compose.yml`'s
  `minio`/`minio-init` services serve a real, versioned manifest from an
  S3-compatible store, so `GET /api/v1/manifest` and
  `POST /api/v1/sign_credential` both work against real (if
  test-fixture) cryptographic material rather than 404ing.
  - The manifest's `public_parameters` and `ooniprobe`'s
    `ANONC_SECRET_KEY` are a matched keypair lifted verbatim from
    `ooniapi/services/ooniprobe/tests/conftest.py`'s `test_creds`
    fixture - the exact pair that service's own `tests/test_anoncred.py`
    already exercises - rather than generated fresh here. That test
    fixture's `age` range (`[2461110, 2826140]`, a Julian-day-number
    range) is deliberately enormous (~1000 years wide starting around
    when that fixture was written), so there's no near-term expiry to
    worry about; if `sign_credential`/`submit_measurement` start failing
    with an age/policy-range error decades from now, that range is where
    to look.
  - `scripts/run-checks.sh` checks both a client-side signal (miniooni's
    own log for the credential-submission fallback warning) and the
    authoritative server-side one (`verification_status` in
    `oonimeasurements`'s response, sourced from `fastpath`'s
    `is_verified` column) - the client log alone isn't proof the ZKP
    proof actually checked out, only that the client didn't give up.
  - The `minio`/`minio-init` services run `pgsty/minio` ("Silo"), a
    community-maintained fork - not `minio/minio`/`minio/mc`, which MinIO
    deleted from Docker Hub on 2026-09-11. See `docker-compose.yml`'s
    comment above the `minio` service for the full story; functionally
    nothing else here changes, since Silo preserves MinIO's S3 API, env
    vars, and CLI conventions (including bundling the client as `mc`).
  - `CONFIG_BUCKET` (used for tor-targets/psiphon-config, see below) is a
    *different* setting from `ANONC_MANIFEST_BUCKET` above, so configuring
    one doesn't incidentally configure the other.
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
