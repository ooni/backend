#!/bin/sh
set -e

# samples a service's tests downloaded into its fixtures/samples, if any
for f in /fixtures/samples/*.sql.gz; do
    [ -e "$f" ] || continue
    gzip -dc "$f" | clickhouse-client
done
