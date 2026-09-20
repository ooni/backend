#!/usr/bin/env bash
#
# Runs the actual e2e assertions against a stack already brought up with
# `docker compose up -d` (see run.sh for the full orchestration, or run
# this directly against a stack you started yourself).
#
# Requires: curl, jq, docker compose v2 (for the `miniooni` step).
#
# NOTE: this deliberately does NOT include a check-in probe_cc validation
# check. That's a regression test for https://github.com/ooni/backend/pull/1145
# (invalid probe_cc should be rejected with 422, not crash ooniprobe with a
# 500 per issue #1144) and would fail against master until that PR merges.
# It's being added directly in that PR instead, so this harness merges with
# green checks and #1145 gets to show the same assertion flip from failing
# to passing within its own diff.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${E2E_DIR}"

ROUTER_URL="http://localhost:${ROUTER_PORT:-8080}"
FAILURES=0

pass() { echo "  PASS: $*"; }
fail() { echo "  FAIL: $*"; FAILURES=$((FAILURES + 1)); }

echo "=== [1/3] router reachable ==="
if curl -fsS "${ROUTER_URL}/health" >/dev/null; then
    pass "router /health responded"
else
    echo "router is not reachable at ${ROUTER_URL} - is the stack up? (docker compose up -d)" >&2
    exit 1
fi

echo "=== [2/3] real client: submit a measurement via containerized miniooni ==="
# `example` is InputNone (no real network target, ~1s synthetic run), so
# this exercises session bootstrap + /api/v1/submit_measurement without
# depending on real-world network conditions or test helpers. It does NOT
# exercise /api/v1/check-in (InputNone experiments never call it) - see the
# note at the top of this file about where check-in gets covered.
MINIOONI_LOG="$(mktemp)"
if docker compose --profile client run --rm miniooni example \
        --probe-services "${ROUTER_URL}" \
        --software-name e2e-harness \
        --no-json \
        --yes 2>&1 | tee "${MINIOONI_LOG}"; then
    :
else
    fail "miniooni exited non-zero running the 'example' experiment"
fi

measurement_uid="$(grep -oE 'explorer\.ooni\.org/m/[A-Za-z0-9_.]+' "${MINIOONI_LOG}" | tail -n1 | sed 's#.*/m/##')"
if [ -z "${measurement_uid}" ]; then
    fail "could not find a measurement UID in miniooni's output (see ${MINIOONI_LOG}); submission likely failed"
else
    pass "miniooni submitted a measurement (uid=${measurement_uid})"
fi

echo "=== [3/3] retrieval: measurement round-trips through fastpath into oonimeasurements ==="
if [ -n "${measurement_uid}" ]; then
    found=0
    # fastpath scores measurements asynchronously, so poll for a bit rather
    # than assuming it has landed the instant submission returns.
    for _ in $(seq 1 30); do
        meta="$(curl -sS "${ROUTER_URL}/api/v1/measurement_meta?measurement_uid=${measurement_uid}")"
        report_id="$(echo "${meta}" | jq -r '.report_id // empty')"
        if [ -n "${report_id}" ]; then
            found=1
            break
        fi
        sleep 2
    done
    if [ "${found}" = "1" ]; then
        pass "measurement_meta returned report_id=${report_id} for uid=${measurement_uid}"
    else
        fail "measurement ${measurement_uid} never became retrievable via /api/v1/measurement_meta after 60s"
    fi
else
    fail "skipped retrieval check: no measurement UID from step 2"
fi

echo
if [ "${FAILURES}" -eq 0 ]; then
    echo "all checks passed"
    exit 0
else
    echo "${FAILURES} check(s) failed"
    exit 1
fi
