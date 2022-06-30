# OONI backend

Welcome. This document describes the architecture of the main components of the
OONI infrastructure.

The documentation is meant for core contributors, external contributors and researcher
that want to extract data or reuse software components in their own projects.

This file is [rendered here](https://ooni.github.io/pipeline/README.html)

You can also explore the [documentation tree](https://ooni.github.io/pipeline/)

## Table of contents

[TOC]

## Architecture

The backend infrastructure provides multiple functions:

* Provide APIs for data consumers
* Instruct probes on what measurements to perform
* Receive measurements from probes, process them and store them in the database and on S3

## Data flow

This diagram represent the main flow of measurement data


blockdiag {
  Probes [color = "#ffeeee"]; 
  Explorer [color = "#eeeeff"]; 
  Probes -> "API: Probe services" -> "Fastpath" -> "DB: fastpath tbl" -> "API: Measurements" -> "Explorer";
  "API: Probe services" -> "disk queue" -> "API uploader" -> "S3 jsonl" -> "API: Measurements";
  "API uploader" -> "S3 postcan";
  "API uploader" -> "DB jsonl tbl";
  "DB jsonl tbl" -> "API: Measurements"
}


Each measurement is processed individually in real time.


## Components: API

The API entry points are documented at [apidocs](https://api.ooni.io/apidocs/)

### Measurements

Provide access to measurements to end users directly and through Explorer.

Mounted under /api/v1/measurement/

The API is versioned. Access is rate limited based on source IP address and access tokens
due to the computational cost of running heavy queries on the database.

[Sources](https://github.com/ooni/api/blob/master/newapi/ooniapi/probe_services.py)

### Probe services

Serves lists of collectors and test helpers to the probes and receive measurements from them.

Mounted under /api/v1/

[Sources](https://github.com/ooni/api/blob/master/newapi/ooniapi/probe_services.py)

### Private entry points

Not for public consumption. Mounted under `/api/_` and used exclusively by Explorer

[Sources](https://github.com/ooni/api/blob/master/newapi/ooniapi/private.py)

## Fastpath

[Documentation](af/fastpath/fastpath/core.html)

## Database

## Operations

### Build, deploy, rollback

Host deployments are done with the [sysadmin repo](https://github.com/ooni/sysadmin)

For component updates a deployment pipeline is used:

Look at the [Status dashboard](https://github.com/ooni/backend/wiki/Backend) - be aware of badge image caching

Use the deploy tool:

```bash
# Update all badges:
dep refresh_badges

# Show status
dep

# Deploy/rollback a given version on the "test" stage
deploy ooni-api test 0.6~pr194-147

# Deploy latest build on the first stage
deploy ooni-api

# Deploy latest build on a given stage
deploy ooni-api prod

```

### Adding new tests

Update [database_upgrade_schema](https://github.com/ooni/pipeline/blob/master/af/fastpath/database_upgrade_schema.py)

```
ALTER TYPE ootest ADD VALUE '<test_name>';
```

Update [fastpath](https://github.com/ooni/pipeline/blob/master/af/fastpath/fastpath/core.py)
by adding a new test to the `score_measurement` function and adding relevant
integration tests.

Create a [Pull Request](https://github.com/ooni/pipeline/compare)

Run fastpath manually from S3 on the testing stage see: [rerun fastpath manually](#rerun-fastpath-manually)

Update the [api](https://github.com/ooni/api/blob/master/newapi/ooniapi/measurements.py#L491)

### Adding new fingerprints

TODO

### API runbook

Monitor the [API](https://mon.ooni.nu/grafana/d/CkdDBscGz/ams-pg-api?orgId=1) and 
[fastpath](https://mon.ooni.nu/grafana/d/75nnWVpMz/fastpath-ams-pg?orgId=1) dashboards.

Follow Nginx or API logs with:
```bash
sudo journalctl -f -u nginx --no-hostname
# The API logs contain SQL queries, exceptions etc
sudo journalctl -f --identifier gunicorn3 --no-hostname
```

### Fastpath runbook

#### Manual deployment

```bash
ssh <host>
sudo apt-get update
apt-cache show fastpath | grep Ver | head -n5
sudo apt-get install fastpath
```

#### Restart
`sudo systemctl restart fastpath`

#### Rerun fastpath manually

Run as fastpath user:

```bash
ssh <host>
sudo sudo -u fastpath /bin/bash
cd
```

```bash
fastpath --help
# rerun without overwriting files on disk nor writing to database:
fastpath --start-day 2016-05-13 --end-day 2016-05-14 --stdout --no-write-msmt --no-write-to-db
# rerun without overwriting files on disk:
fastpath --start-day 2016-05-13 --end-day 2016-05-14 --stdout --no-write-msmt
# rerun and overwrite:
fastpath --start-day 2016-05-13 --end-day 2016-05-14 --stdout --update
```

The fastpath will pull cans from S3.
The daemon (doing real-time processing) can keep running in the meantime.

[Progress chart](https://mon.ooni.nu/prometheus/new/graph?g0.expr=netdata_statsd_gauge_fastpath_s3feeder_s3_download_percentage_value_average%7Bdimension%3D%22gauge%22%7D&g0.tab=0&g0.stacked=1&g0.range_input=2h&g1.expr=netdata_statsd_gauge_fastpath_load_s3_reports_remaining_files_value_average%7Bdimension%3D%22gauge%22%7D&g1.tab=0&g1.stacked=1&g1.range_input=1h)
#### Log monitoring

```bash
sudo journalctl -f -u fastpath
```

#### Monitoring dashboard

[https://mon.ooni.nu/grafana/d/75nnWVpMz/fastpath-ams-pg?orgId=1&refresh=5m&from=now-7d&to=now](https://mon.ooni.nu/grafana/d/75nnWVpMz/fastpath-ams-pg?orgId=1&refresh=5m&from=now-7d&to=now)

### Analysis runbook

The Analysis tool runs a number of systemd timers to monitor the slow query summary and more.
See https://github.com/ooni/pipeline/blob/master/af/analysis/analysis/analysis.py

#### Manual deployment

```
ssh <host>
sudo apt-get update
apt-cache show analysis | grep Ver | head -n5
sudo apt-get install analysis=<version>
```

#### Run manually
```
sudo systemctl restart ooni-update-counters.service
```

#### Log monitoring

```
sudo journalctl -f --identifier analysis
```

#### Monitoring dashboard

[https://mon.ooni.nu/grafana/d/75nnWVpMz/fastpath-ams-pg?orgId=1&refresh=5m&from=now-7d&to=now](https://mon.ooni.nu/grafana/d/75nnWVpMz/fastpath-ams-pg?orgId=1&refresh=5m&from=now-7d&to=now)

### Deploy new host

Deploy host from https://cloud.digitalocean.com/projects/

Create DNS "A" record `<name>.ooni.org` at https://ap.www.namecheap.com/

On the sysadmin repo, ansible directory, add the host to the inventory

Run the deploy with the root SSH user
```
./play deploy-<foo>.yml -l <name>.ooni.org --diff -u root
```

Update prometheus
```
./play deploy-prometheus.yml -t prometheus-conf --diff
```
