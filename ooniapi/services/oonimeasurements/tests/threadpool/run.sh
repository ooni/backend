#!/bin/bash
# Thread-pool starvation load test for API token lookups (see README.md).
# Usage: [SCENARIOS="baseline flood-stop ..."] run.sh [<ooniapi dir>] <results.jsonl>
# Needs podman (the ClickHouse binary comes from an image mount). Runs one
# container, removed afterwards; the image is kept and tagged by its inputs.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
SERVICE=$(cd "$HERE/../.." && pwd)
if [ $# -ge 2 ]; then SRC=$(cd "$1" && pwd); shift; else SRC=$(cd "$SERVICE/../.." && pwd); fi
OUT=$1
CHIMG=docker.io/clickhouse/clickhouse-server:25.8.29.51
TAG=$(cat "$HERE/Containerfile" "$SERVICE/pyproject.toml" | sha256sum | cut -c1-12)
IMG=localhost/oonimeasurements-threadpool-test:$TAG
podman image exists $IMG || podman build -q -t $IMG -f "$HERE/Containerfile" "$SERVICE"
podman image exists $CHIMG || podman pull -q $CHIMG
podman run --rm --pull=never --name oonimeasurements-threadpool-test \
    --cap-add NET_ADMIN,NET_RAW --ulimit nofile=65536:65536 -e SCENARIOS="${SCENARIOS:-all}" \
    -v "$SRC:/src:ro" -v "$HERE:/harness:ro" \
    --mount type=image,source=$CHIMG,target=/chimg \
    $IMG bash /harness/inner.sh | tee "$OUT"
python3 "$HERE/summarize.py" "$OUT"
