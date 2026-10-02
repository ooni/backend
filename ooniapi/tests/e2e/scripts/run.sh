#!/usr/bin/env bash
#
# Full end-to-end run: build images, bring the stack up, wait for it to be
# healthy, run the assertions, then always tear down. This is what CI calls;
# it's also the easiest way to run the harness locally.
#
# Usage:
#   ./scripts/run.sh                 # build + up + test + down
#   SKIP_BUILD=1 ./scripts/run.sh    # reuse images already built
#   KEEP_UP=1 ./scripts/run.sh       # leave the stack running after the run
#                                    # (e.g. to poke at it / read logs by hand)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${E2E_DIR}"

cleanup() {
    status=$?
    if [ "${status}" -ne 0 ] || [ "${DUMP_LOGS_ALWAYS:-0}" = "1" ]; then
        echo "=== docker compose logs (last 200 lines/service) ==="
        docker compose logs --tail=200 || true
    fi
    if [ "${KEEP_UP:-0}" != "1" ]; then
        echo "=== tearing down ==="
        docker compose down -v --remove-orphans || true
    fi
    exit "${status}"
}
trap cleanup EXIT

if [ "${SKIP_BUILD:-0}" != "1" ]; then
    echo "=== building ooniapi service images ==="
    ./scripts/build-images.sh
fi

echo "=== building miniooni (probe-cli ref: ${PROBE_CLI_REF:-master}) ==="
docker compose build miniooni

echo "=== starting stack ==="
docker compose up -d --wait --wait-timeout 180

echo "=== running checks ==="
./scripts/run-checks.sh
