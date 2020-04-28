#!/bin/bash

if [ -z "$POSTGRES_HOST" ]; then
    export POSTGRES_HOST=localhost
fi

set -exuo pipefail
tmpdir=$(mktemp -d)
cd $tmpdir
git clone --depth 1 https://github.com/ooni/pipeline.git

echo "Create ooni_measurements database"
psql -c 'create database ooni_measurements;' -U postgres -h $POSTGRES_HOST

echo "Create amsapi and readonly roles"
psql -U postgres -h $POSTGRES_HOST ooni_measurements -c "CREATE ROLE amsapi;"
psql -U postgres -h $POSTGRES_HOST ooni_measurements -c "CREATE ROLE readonly;"

echo "Creating database tables using SQL files:"
ls pipeline/af/oometa/*.install.sql
cat pipeline/af/oometa/*.install.sql | psql -U postgres -h $POSTGRES_HOST ooni_measurements -v ON_ERROR_STOP=1
