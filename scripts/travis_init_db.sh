#!/bin/bash
set -exuo pipefail
tmpdir=$(mktemp -d)
cd $tmpdir
git clone --depth 1 https://github.com/ooni/pipeline.git

echo "Create ooni_measurements database"
psql -c 'create database ooni_measurements;' -U postgres

echo "Create amsapi and readonly roles"
psql -U postgres ooni_measurements -c "CREATE ROLE amsapi;"
psql -U postgres ooni_measurements -c "CREATE ROLE readonly;"

echo "Creating database tables using SQL files:"
ls pipeline/af/oometa/*.install.sql
cat pipeline/af/oometa/*.install.sql | psql -U postgres ooni_measurements -v ON_ERROR_STOP=1
