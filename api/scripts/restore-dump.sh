lz4cat meta-closure.sql.lz4 | psql -U postgres -h localhost -p 5433 measurements -f sample-dump.sql

