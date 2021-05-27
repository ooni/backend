#!/bin/bash
set -exuo pipefail

export POSTGRES_HOST=db
export PGPASSWORD=$POSTGRES_PASSWORD

tmpdir=$(mktemp -d)
cd $tmpdir
git clone --depth 1 https://github.com/ooni/pipeline.git

echo "Create amsapi and readonly roles"
psql -U $POSTGRES_USER -h $POSTGRES_HOST $POSTGRES_USER -c "CREATE ROLE amsapi;"
psql -U $POSTGRES_USER -h $POSTGRES_HOST $POSTGRES_USER -c "CREATE ROLE readonly;"

echo "Creating database tables using SQL files:"
ls pipeline/af/oometa/*.install.sql
cat pipeline/af/oometa/*.install.sql | psql -U $POSTGRES_USER -h $POSTGRES_HOST $POSTGRES_USER -v ON_ERROR_STOP=1
