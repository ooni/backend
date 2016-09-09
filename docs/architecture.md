# OONI data processing pipeline architecture

This document explains the current architecture of the OONI data processing
pipeline.

The machines involved in the data processing pipelines are mainly 4:

* bouncer.ooni: the measurement collector and bouncer. This what probes connect
  to either via a Tor Hidden Service or HTTPS and submit measurements to.

* chameleon.ooni: this is the machine that is responsible for ingesting measurement
  data from the collector(s), normalizing it and preparing it for insertion
  inside of the database.

* hammerhead.ooni: this is the machine that hosts our database and will have a
  certain amount of load while it updates the materialised views.

* measurements.ooni: this is the machine that hosts the web server exposing the raw
  sanitised and normalised measurements so that people can download them in bulk
  from https://measurements.ooni.torproject.org/

The flow chart below illustrates the various stages of the data processing
pipeline.

![Flow chart](https://raw.githubusercontent.com/TheTorProject/ooni-pipeline/21c2923c12fd1db79dfec000fbf2d05130bafc9f/docs/ooni-pipeline-architecture.png)

The light green labels prefixed by `M H * * *` indicate a daily task scheduled via
cron that runs at minute `M` and hour `H`.

For example the "rename reports" task is scheduled to run at 00:30 (half past
midnight) every day, while the batch pipeline task is scheduled to run at 04:00
(4 AM) every day.

I will now enumerate what each task is responsible for doing.

## 1 - reports results

This is something that happens continously whenever a measurement is run by an
ooniprobe.
The collector service receives all these measurements and while a measurement
is in progress (the probe has not yet called the close method), they are kept
inside of a staging directory.

Once the probe calls the close, or a pre-defined maximum interval of time
passes since the last update (current set to 1 hour) they are archived inside
of the `/data/bouncer/archive/` directory.


## 2 - rename reports

Reports are move from the `/data/bouncer/archive` directory into another directory
where the collector can fetch them from.
In doing so transformations are applied to the filename in order to write them in
the correct format that the pipeline expects. This file format is:

`${YEAR}${MONTH}${DAY}T${HOUR}${MINUTE}${SECOND}-${TEST_NAME}-${REPORT_ID}-${ASN}-${COUNTRY_CODE}-probe-${DATA_FORMAT_VERSION}.${EXTENSION}`

Where extension can be one of `.json` or `.yaml`.

This also serves to ensure that we only end up processing measurements that
were finalised up until 00:30.

## 3 - rsync reports

The data pipeline machine connects to the bouncer and looks inside of the
directory where the submitted reports have been staged and rsyncs them over to it's
own staging directory (`/data/ooni/private/reports-raw/yaml`). The report files are
deleted once they have been copied over.

Every time a new batch of reports are copied over they are placed inside of
a directory which is identified by the current date (ex
`/data/ooni/private/reports-raw/yaml/2016-08-01`).
This date is what we call a "bucket" and is kept track of in the database
as the column `bucket_date`.

The reason why we do this is so that we can selectively re-run processing
on measurements for a particular time period, without having to re-run the
processing on all data.

This is especially useful since many older reports are stored in YAML and
going through them is very CPU intensive, while that is not the case with
more recent JSON based reports.


## 4 - backup to s3

The raw reports are backed up to a private amazon s3 bucket. This process
happens concurrently to the running of the other stages of the data processing
pipeline.

## 5 - normalise

The reports in the staging directory (`/data/ooni/private/reports-raw/`) are
taken and normalised so that they all follow the same data format.

This is to take into account the various changes that have happened in the OONI
data format and to continue accepting measurements from older probes.

## 6 - sanitise

The goal of this stage is to remove any information that we may not want to
publish in the public reports.
Currently all that we do here is replace bridge IP addresses with their hash
by looking up their IP address is a database we keep of the private bridges
we have used in testing.

## 7 - load into DB

Here what we do is generate a CSV version of the fields to be inserted into
the database and use the `COPY FROM ` PostGres method to efficiently load
them into the database.

Currently all the fields are inserted into a single table that has the
following schema:

```
id  uuid
input   text
report_id   text
report_filename text
options jsonb
probe_cc    text
probe_asn   text
probe_ip    text
data_format_version text
test_name   text
test_start_time timestamp
measurement_start_time  timestamp
test_runtime    real
software_name   text
software_version    text
test_version    text
bucket_date date
test_helpers    jsonb
test_keys   jsonb
```

The meaning of these values are for a large part described 
inside of
[ooni-spec](https://github.com/TheTorProject/ooni-spec/blob/master/data-formats/df-000-base.md).
Some special values are `test_keys` that represent everything that doesn't fit
inside of the top level data format and is specific to this type of measurement
and `bucket_date` which is the date in which the measurements where collected.

Indexes are created for the following columns:

```
CREATE UNIQUE INDEX metrics_new_pkey ON metrics USING btree (id)
CREATE INDEX probe_cc_idx ON metrics USING btree (probe_cc)
CREATE INDEX input_idx ON metrics USING btree (input)
CREATE INDEX test_start_time_idx ON metrics USING btree (test_start_time)
CREATE INDEX test_name_idx ON metrics USING btree (test_name)
CREATE INDEX report_id_idx ON metrics USING btree (report_id)
```

## 8 - publish

A batch operation run hourly on the measurements.ooni server takes the
sanitised reports and publishes them on
`https://measurements.ooni.torproject.org/`.

## 9 - refresh materialized views

We have the following materialised views that are updated on a daily basis.

These materialised views are the core of what powers the visualisations in
the OONI explorer.

The blockpage detection heuristics are currently in the form of
`SELECT LIKE %%` statements that can be applied to either the HTTP response headers
or the HTTP response body.

They are defined inside of this file:
**bodies**: https://github.com/TheTorProject/ooni-pipeline/blob/master/pipeline/batch/sql_tasks.py#L11
**fingerprints**: https://github.com/TheTorProject/ooni-pipeline/blob/master/pipeline/batch/sql_tasks.py#L27

### Blockpage count

This materialised view tells us the number of pages where we have identified
a blockpage and the total number of pages tested during that particular test
run.

The columns in the view are:

```
block_count
total_count
report_id
test_start_time
probe_cc
probe_asn
```

The actual SQL for the materialised view is generated using this very ugly code
here: https://github.com/TheTorProject/ooni-pipeline/blob/master/pipeline/batch/sql_tasks.py#L168


### Blockpage URLs

This keeps track of which where detected as being blocked from which countries
and networks.

The columns of the view are:

```
input
report_id
test_start_time
probe_cc
probe_asn
```

The SQL for the materialised view is generated by this code here:
https://github.com/TheTorProject/ooni-pipeline/blob/master/pipeline/batch/sql_tasks.py#L173

### Country counts

This view is used to keep track of the total number of measurements collected
from each country.

The columns are:

```
probe_cc
count
```

### Identified vendors

This materialised view keeps track of which proxy vendors we have identified in
which countries.

We currently support 3 types of proxies, bluecoat, privoxy and squid and the
fingerprints for them are fairly simple and can be found here:
https://github.com/TheTorProject/ooni-pipeline/blob/master/pipeline/batch/sql_tasks.py#L187
https://github.com/TheTorProject/ooni-pipeline/blob/master/pipeline/batch/sql_tasks.py#L195
https://github.com/TheTorProject/ooni-pipeline/blob/master/pipeline/batch/sql_tasks.py#L212

The columns are:

```
test_start_time
probe_cc
probe_asn
report_id
vendor
```

Where vendor can be one of "bluecoat", "privoxy" or "squid".
