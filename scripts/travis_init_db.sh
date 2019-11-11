#!/bin/bash
set -exuo pipefail
tmpdir=$(mktemp -d)
cd $tmpdir
git clone --depth 1 https://github.com/ooni/pipeline.git
psql -c 'create database ooni_measurements;' -U postgres
echo "Creating database tables using SQL files:"
ls pipeline/af/oometa/*.install.sql
cat pipeline/af/oometa/*.install.sql | psql -U postgres ooni_measurements -v ON_ERROR_STOP=1
