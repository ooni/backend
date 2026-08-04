#!/bin/sh
set -e

gzip -dc /fixtures/samples/obs_web-sample.sql.gz | clickhouse-client
gzip -dc /fixtures/samples/analysis_web_measurement-sample.sql.gz | clickhouse-client