#!/bin/bash
set -eu

# Backup database schema and tables to S3
# debdeps: postgresql-client-11 zstd s4cmd

# Monitor with journalctl -t pg-backup

PG_USER="shovel"
DBNAME="metadb"

BUCKET="s3://ooni-data-eu-fra"

TS=$(date +%Y%m%d)

echo "Running PG backup on $TS" | systemd-cat -t pg-backup

# TODO: use dedicated conf
S3_ACCESS_KEY=$(awk -F "=" '/^aws_access_key_id/ {print $2}' /etc/ooni/api-uploader.conf)
S3_SECRET_KEY=$(awk -F "=" '/^aws_secret_access_key/ {print $2}' /etc/ooni/api-uploader.conf)

echo "Create database and the whole schema, without data. SQL format" | systemd-cat -t pg-backup
pg_dump -U $PG_USER $DBNAME --create --schema-only > setup_db.sql

echo "Dump selected tables, without the schema, into a compressed file" | systemd-cat -t pg-backup
pg_dump -U $PG_USER $DBNAME --data-only --format=custom -t autoclavedlookup -t citizenlab -t fastpath -t jsonl --compress=0 | zstdmt -6 > data.zstd

s4cmd -f --retry=100 put setup_db.sql "$BUCKET/pg_backup/$TS/"
s4cmd -f --retry=100 put data.zstd "$BUCKET/pg_backup/$TS/"

rm setup_db.sql
rm data.zstd

echo "PG backup on $TS completed" | systemd-cat -t pg-backup
