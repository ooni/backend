#!/bin/sh
set -e

gzip -dc /fixtures/obs_web-sample.sql.gz | clickhouse-client
gzip -dc /fixtures/analysis_web_measurement-sample.sql.gz | clickhouse-client