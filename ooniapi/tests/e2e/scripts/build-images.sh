#!/usr/bin/env bash
#
# Builds the ooniapi service images used by docker-compose.yml.
#
# This deliberately delegates to each service's own `make docker-build`
# rather than using `docker compose build`: every service's Dockerfile
# COPYs a `common` directory that is actually a symlink out to
# ooniapi/common/src/common, and only the tar-based trick in each
# service's own Makefile (`tar -czh . | docker build ... -`) dereferences
# that symlink correctly before it reaches the docker daemon. Reimplementing
# that here would just be duplicating logic that's already
# maintained in ooniapi/services/*/Makefile.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OONIAPI_DIR="$(cd "${E2E_DIR}/../.." && pwd)"

SERVICES=(ooniauth oonifindings oonimeasurements ooniprobe oonirun testlists)
ENV_LABEL="${ENV_LABEL:-e2e}"

for svc in "${SERVICES[@]}"; do
    svc_dir="${OONIAPI_DIR}/services/${svc}"
    if [ ! -d "${svc_dir}" ]; then
        echo "error: expected service directory not found: ${svc_dir}" >&2
        exit 1
    fi
    echo "==> building ${svc} (image ooni-e2e/${svc}:${ENV_LABEL})"
    make -C "${svc_dir}" docker-build \
        IMAGE_NAME="ooni-e2e/${svc}" \
        ENV_LABEL="${ENV_LABEL}"
done

echo "==> all ooniapi service images built with tag :${ENV_LABEL}"
