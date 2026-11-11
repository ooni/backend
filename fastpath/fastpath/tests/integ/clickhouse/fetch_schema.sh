#!/bin/sh
# Download production's ClickHouse schema from ooni/devops, at a pinned commit,
# to the file given as the first argument.
# Override the commit with DEVOPS_SCHEMA_REF.
set -eu
ref=${DEVOPS_SCHEMA_REF:-d5ffb0948de5e54e7198e843a0df9a4ecc153783}
out=$1
curl -fsSL -o "$out.tmp" \
    "https://raw.githubusercontent.com/ooni/devops/$ref/scripts/cluster-migration/schema.sql"
mv "$out.tmp" "$out"
