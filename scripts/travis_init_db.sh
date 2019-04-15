#!/bin/bash
set -ex
tmpdir=$(mktemp -d)
cd $tmpdir
git clone --depth 1 --branch ooexplr-meta https://github.com/ooni/pipeline.git
psql -c 'create database ooni_measurements;' -U postgres
cat af/oometa/*.install.sql | psql -U postgres ooni_measurements
