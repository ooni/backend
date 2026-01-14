# Database

**ATTENTION** We have since switched to using PostgreSQL instead of EmbeddedRocksDB, so parts of this documentation needs updating.

The backend uses both the native ClickHouse table engine MergeTree and
\"foreign\" database engines, for example in EmbeddedRocksDB tables.

The MergeTree family is column-oriented, **eventually consistent**,
**non-transactional** and optimized for OLAP workloads. It is suitable
for very large number of records and columns.

The existing tables using MergeTree are meant to support replication in
future by switching to ReplicatedMergeTree. This is crucial to implement
active/standby and even active/active setups both for increased
reliability and performance.

This choice is reflected in how record insertion and deduplication are
performed: where possible, the API codebase assumes that multiple API
instances can insert and fetch records without leading to inconsistent
results. This requires special care in the implementation because
MergeTree tables do not support **immediate** consistency nor
transactions.

EmbeddedRocksDB uses <https://rocksdb.org/> - a key-value, row-oriented,
low-latency engine. Some backend workloads are more suitable for this
engine. EmbeddedRocksDB **does not support replication**.

> **important**
> Some workloads would better suited for a transactional and immediately
> consistent database. E.g. [OONI Run](#ooni-run)&thinsp;🐝 and
> [Incident management](#incident-management)&thinsp;🐝. See
> <https://clickhouse.com/docs/en/engines/table-engines/special/keeper-map>

To get an overview of the existing tables and engines use:

    SELECT engine, name FROM system.tables WHERE database = 'default' ORDER BY engine, name

An overview of the more important tables:

- [accounts table](#accounts-table)&thinsp;⛁ EmbeddedRocksDB

- [asnmeta table](#asnmeta-table)&thinsp;⛁ MergeTree

- [citizenlab table](#citizenlab-table)&thinsp;⛁ ReplacingMergeTree

- [citizenlab_flip table](#citizenlab_flip-table)&thinsp;⛁ ReplacingMergeTree

- [counters_asn_test_list table](#counters_asn_test_list-table)&thinsp;⛁
  MaterializedView

- [counters_test_list table](#counters_test_list-table)&thinsp;⛁ MaterializedView

- [fastpath table](#fastpath-table)&thinsp;⛁ ReplacingMergeTree

- [fingerprints_dns table](#fingerprints_dns-table)&thinsp;⛁ EmbeddedRocksDB

- [fingerprints_dns_tmp table](#fingerprints_dns_tmp-table)&thinsp;⛁
  EmbeddedRocksDB

- [fingerprints_http table](#fingerprints_http-table)&thinsp;⛁ EmbeddedRocksDB

- [fingerprints_http_tmp table](#fingerprints_http_tmp-table)&thinsp;⛁
  EmbeddedRocksDB

- [incidents table](#incidents-table)&thinsp;⛁ ReplacingMergeTree

- [jsonl table](#jsonl-table)&thinsp;⛁ MergeTree

- [msmt_feedback table](#msmt_feedback-table)&thinsp;⛁ ReplacingMergeTree

- [oonirun table](#oonirun-table)&thinsp;⛁ ReplacingMergeTree

- [test_groups table](#test_groups-table)&thinsp;⛁ Join

- [url_priorities table](#url_priorities-table)&thinsp;⛁ CollapsingMergeTree

> **note**
> As ClickHouse does not support transactions, there are some workarounds
> to implement atomic updates of whole tables.

One way is to use two tables with the same schema, where one table
receive updates and another one is used for reading, and swap them once
the writes are completed. This is used by the [API](#api)&thinsp;⚙,
[Test helper rotation](#test-helper-rotation)&thinsp;⚙ and other components. The
SQL syntax is:

```sql
EXCHANGE TABLES <a> AND <b>
```

#### accounts table

Used for authentication. Assignes roles to accounts (by account id). The
default value for accounts not present in the table is \"user\". As
such, the table is currently tracking only admin roles.

Schema:

```sql
CREATE TABLE default.accounts
(
    `account_id` FixedString(32),
    `role` String,
    `update_time` DateTime DEFAULT now()
)
ENGINE = EmbeddedRocksDB
PRIMARY KEY account_id
```

To create and update account roles see:

[Creating admin API accounts](#creating-admin-api-accounts)&thinsp;📒

#### asnmeta table

Contains [ASN](#asn)&thinsp;💡 lookup data used by the API

Schema:

```sql
CREATE TABLE default.asnmeta
(
    `asn` UInt32,
    `org_name` String,
    `cc` String,
    `changed` Date,
    `aut_name` String,
    `source` String
)
ENGINE = MergeTree
ORDER BY (asn, changed)
SETTINGS index_granularity = 8192
```

#### asnmeta_tmp table

Temporary table, see [asnmeta table](#asnmeta-table)&thinsp;⛁

Schema:

```sql
CREATE TABLE default.blocking_events
(
    `test_name` String,
    `input` String,
    `probe_cc` String,
    `probe_asn` Int32,
    `status` String,
    `time` DateTime64(3),
    `detection_time` DateTime64(0) MATERIALIZED now64()
)
ENGINE = ReplacingMergeTree
ORDER BY (test_name, input, probe_cc, probe_asn, time)
SETTINGS index_granularity = 4
```

Schema:

```sql
CREATE TABLE default.blocking_status
(
    `test_name` String,
    `input` String,
    `probe_cc` String,
    `probe_asn` Int32,
    `confirmed_perc` Float32,
    `pure_anomaly_perc` Float32,
    `accessible_perc` Float32,
    `cnt` Float32,
    `status` String,
    `old_status` String,
    `change` Float32,
    `stability` Float32,
    `update_time` DateTime64(0) MATERIALIZED now64()
)
ENGINE = ReplacingMergeTree
ORDER BY (test_name, input, probe_cc, probe_asn)
SETTINGS index_granularity = 4
```

#### citizenlab table

Contains data from the
[CitizenLab URL testing list repository](https://github.com/citizenlab/test-lists).

Schema:

```sql
CREATE TABLE default.citizenlab
(
    `domain` String,
    `url` String,
    `cc` FixedString(32),
    `category_code` String
)
ENGINE = ReplacingMergeTree
ORDER BY (domain, url, cc, category_code)
SETTINGS index_granularity = 4
```

Receive writes from [CitizenLab test list updater](#citizenlab-test-list-updater)&thinsp;⚙

Used by [CitizenLab](#citizenlab)&thinsp;🐝

#### citizenlab_flip table

Temporary table. See [CitizenLab test list updater](#citizenlab-test-list-updater)&thinsp;⚙

#### counters_asn_test_list table

A `MATERIALIZED VIEW` table that, despite the name, is updated
continuously by ClickHouse as new measurements are inserted in the
`fastpath` table.

It contains statistics on the incoming measurement flow, grouped by
week, `probe_cc`, `probe_asn` and `input`. It is used by
[Prioritization](#prioritization)&thinsp;🐝.

Schema:

```sql
CREATE MATERIALIZED VIEW default.counters_asn_test_list
(
    `week` DateTime,
    `probe_cc` String,
    `probe_asn` UInt64,
    `input` String,
    `msmt_cnt` UInt64
)
ENGINE = SummingMergeTree
ORDER BY (probe_cc, probe_asn, input)
SETTINGS index_granularity = 8192 AS
SELECT
    toStartOfWeek(measurement_start_time) AS week,
    probe_cc,
    probe_asn,
    input,
    count() AS msmt_cnt
FROM default.fastpath
INNER JOIN default.citizenlab ON fastpath.input = citizenlab.url
WHERE (measurement_start_time < now()) AND (measurement_start_time > (now() - toIntervalDay(8))) AND (test_name = \'web_connectivity\')
GROUP BY week, probe_cc, probe_asn, input
```

#### counters_test_list table

Similar to [counters_asn_test_list table](#counters_asn_test_list-table)&thinsp;⛁ -
the main differences are that this table has daily granularity and does
not discriminate by `probe_asn`

Schema:

```sql
CREATE MATERIALIZED VIEW default.counters_test_list
(
    `day` DateTime,
    `probe_cc` String,
    `input` String,
    `msmt_cnt` UInt64
)
ENGINE = SummingMergeTree
PARTITION BY day
ORDER BY (probe_cc, input)
SETTINGS index_granularity = 8192 AS
SELECT
    toDate(measurement_start_time) AS day,
    probe_cc,
    input,
    count() AS msmt_cnt
FROM default.fastpath
INNER JOIN default.citizenlab ON fastpath.input = citizenlab.url
WHERE (measurement_start_time < now()) AND (measurement_start_time > (now() - toIntervalDay(8))) AND (test_name = \'web_connectivity\')
GROUP BY day, probe_cc, input
```

#### fastpath table

This table stores the output of the [Fastpath](#fastpath)&thinsp;⚙. It is
usually the largest table in the database and receives the largest
amount of read and write traffic.

It is used by multiple entry points in the [API](#api)&thinsp;⚙, primarily
for measurement listing and presentation and by the
[Aggregation and MAT](#aggregation-and-mat)&thinsp;🐝

Schema:

```sql
CREATE TABLE default.fastpath
(
    `measurement_uid` String,
    `report_id` String,
    `input` String,
    `probe_cc` LowCardinality(String),
    `probe_asn` Int32,
    `test_name` LowCardinality(String),
    `test_start_time` DateTime,
    `measurement_start_time` DateTime,
    `filename` String,
    `scores` String,
    `platform` String,
    `anomaly` String,
    `confirmed` String,
    `msm_failure` String,
    `domain` String,
    `software_name` String,
    `software_version` String,
    `control_failure` String,
    `blocking_general` Float32,
    `is_ssl_expected` Int8,
    `page_len` Int32,
    `page_len_ratio` Float32,
    `server_cc` String,
    `server_asn` Int8,
    `server_as_name` String,
    `update_time` DateTime64(3) MATERIALIZED now64(),
    `test_version` String,
    `architecture` String,
    `engine_name` LowCardinality(String),
    `engine_version` String,
    `test_runtime` Float32,
    `blocking_type` String,
    `test_helper_address` LowCardinality(String),
    `test_helper_type` LowCardinality(String),
    INDEX fastpath_rid_idx report_id TYPE minmax GRANULARITY 1,
    INDEX measurement_uid_idx measurement_uid TYPE minmax GRANULARITY 8
)
ENGINE = ReplacingMergeTree(update_time)
ORDER BY (measurement_start_time, report_id, input, measurement_uid)
SETTINGS index_granularity = 8192
```

See [Fastpath deduplication](#fastpath-deduplication)&thinsp;📒 for deduplicating the table
records.

#### fingerprints_dns table

Stores measurement DNS fingerprints. The contents are used by the
[Fastpath](#fastpath)&thinsp;⚙ to detect `confirmed` measurements.

It is updated by the [Fingerprint updater](#fingerprint-updater)&thinsp;⚙

Schema:

```sql
CREATE TABLE default.fingerprints_dns
(
    `name` String,
    `scope` Enum8(\'nat\' = 1, \'isp\' = 2, \'prod\' = 3, \'inst\' = 4, \'vbw\' = 5, \'fp\' = 6),
    `other_names` String,
    `location_found` String,
    `pattern_type` Enum8(\'full\' = 1, \'prefix\' = 2, \'contains\' = 3, \'regexp\' = 4),
    `pattern` String,
    `confidence_no_fp` UInt8,
    `expected_countries` String,
    `source` String,
    `exp_url` String,
    `notes` String
)
ENGINE = EmbeddedRocksDB
PRIMARY KEY name
```

#### fingerprints_dns_tmp table

Temporary table. See [Fingerprint updater](#fingerprint-updater)&thinsp;⚙

#### fingerprints_http table

Stores measurement HTTP fingerprints. The contents are used by the
[Fastpath](#fastpath)&thinsp;⚙ to detect `confirmed` measurements.

It is updated by the [Fingerprint updater](#fingerprint-updater)&thinsp;⚙

Schema:

```sql
CREATE TABLE default.fingerprints_http
(
    `name` String,
    `scope` Enum8(\'nat\' = 1, \'isp\' = 2, \'prod\' = 3, \'inst\' = 4, \'vbw\' = 5, \'fp\' = 6, \'injb\' = 7, \'prov\' = 8),
    `other_names` String,
    `location_found` String,
    `pattern_type` Enum8(\'full\' = 1, \'prefix\' = 2, \'contains\' = 3, \'regexp\' = 4),
    `pattern` String,
    `confidence_no_fp` UInt8,
    `expected_countries` String,
    `source` String,
    `exp_url` String,
    `notes` String
)
ENGINE = EmbeddedRocksDB
PRIMARY KEY name
```

#### fingerprints_http_tmp table

Temporary table. See [Fingerprint updater](#fingerprint-updater)&thinsp;⚙

#### incidents table

Stores incidents. See [Incident management](#incident-management)&thinsp;🐝.

Schema:

```sql
CREATE TABLE default.incidents
(
    `update_time` DateTime DEFAULT now(),
    `start_time` DateTime DEFAULT now(),
    `end_time` Nullable(DateTime),
    `creator_account_id` FixedString(32),
    `reported_by` String,
    `id` String,
    `title` String,
    `text` String,
    `event_type` LowCardinality(String),
    `published` UInt8,
    `deleted` UInt8 DEFAULT 0,
    `CCs` Array(FixedString(2)),
    `ASNs` Array(UInt32),
    `domains` Array(String),
    `tags` Array(String),
    `links` Array(String),
    `test_names` Array(String),
    `short_description` String,
    `email_address` String,
    `create_time` DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(update_time)
ORDER BY id
SETTINGS index_granularity = 1
```

#### jsonl table

This table provides a method to look up measurements in
[JSONL files](#topic:jsonl) stored in [S3 data bucket](#s3-data-bucket)&thinsp;💡 buckets.

It is written by the [Measurement uploader](#measurement-uploader)&thinsp;⚙ when
[Postcans](#topic:postcans) and [JSONL files](#jsonl-files)&thinsp;💡 just after
measurements are uploaded to the bucket.

It is used by multiple entry points in the [API](#api)&thinsp;⚙, primarily
by `get_measurement_meta`.

<https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/api/ooniapi/measurements.py#L470>

Schema:

```sql
CREATE TABLE default.jsonl
(
    `report_id` String,
    `input` String,
    `s3path` String,
    `linenum` Int32,
    `measurement_uid` String,
    `date` Date,
    `source` String,
    `update_time` DateTime64(3) MATERIALIZED now64()
)
ENGINE = ReplacingMergeTree(update_time)
ORDER BY (report_id, input, measurement_uid)
SETTINGS index_granularity = 8192
```

#### msmt_feedback table

Used for [Measurement feedback](#measurement-feedback)&thinsp;🐝

Schema:

```sql
CREATE TABLE default.msmt_feedback
(
    `measurement_uid` String,
    `account_id` String,
    `status` String,
    `update_time` DateTime64(3) MATERIALIZED now64(),
    `comment` String
)
ENGINE = ReplacingMergeTree
ORDER BY (measurement_uid, account_id)
SETTINGS index_granularity = 4
```

#### oonirun table

Used for [OONI Run](#ooni-run)&thinsp;🐝

Schema:

```sql
CREATE TABLE default.oonirun
(
    `ooni_run_link_id` UInt64,
    `descriptor_creation_time` DateTime64(3),
    `translation_creation_time` DateTime64(3),
    `creator_account_id` FixedString(32),
    `archived` UInt8 DEFAULT 0,
    `descriptor` String,
    `author` String,
    `name` String,
    `short_description` String,
    `icon` String
)
ENGINE = ReplacingMergeTree(translation_creation_time)
ORDER BY (ooni_run_link_id, descriptor_creation_time)
SETTINGS index_granularity = 1
```

#### obs_openvpn table

Table used by OpenVPN tests. Written by the [Fastpath](#fastpath)&thinsp;⚙
and read by the [API](#api)&thinsp;⚙

Schema:

```sql
CREATE TABLE default.obs_openvpn
(
    `anomaly` Int8,
    `bootstrap_time` Float32,
    `confirmed` Int8,
    `error` String,
    `failure` String,
    `input` String,
    `last_handshake_transaction_id` Int32,
    `measurement_start_time` DateTime,
    `measurement_uid` String,
    `minivpn_version` String,
    `obfs4_version` String,
    `obfuscation` String,
    `platform` String,
    `probe_asn` Int32,
    `probe_cc` String,
    `probe_network_name` String,
    `provider` String,
    `remote` String,
    `report_id` String,
    `resolver_asn` Int32,
    `resolver_ip` String,
    `resolver_network_name` String,
    `software_name` String,
    `software_version` String,
    `success` Int8,
    `success_handshake` Int8,
    `success_icmp` Int8,
    `success_urlgrab` Int8,
    `tcp_connect_status_success` Int8,
    `test_runtime` Float32,
    `test_start_time` DateTime,
    `transport` String
)
ENGINE = ReplacingMergeTree
ORDER BY (measurement_start_time, report_id, input)
SETTINGS index_granularity = 8
```

#### test_groups table

Contains the definition of test groups. Updated manually and read by the
[API](#comp:api), mainly to show grouping in [Explorer](#explorer)&thinsp;🖱.

Schema:

```sql
CREATE TABLE default.test_groups
(
    `test_name` String,
    `test_group` String
)
ENGINE = Join(ANY, LEFT, test_name)
```

#### test_helper_instances table

List of live, draining and destroyed test helper instances. Used by
[Test helper rotation](#test-helper-rotation)&thinsp;⚙ internally.

Schema:

```sql
CREATE TABLE default.test_helper_instances
(
    `rdn` String,
    `dns_zone` String,
    `name` String,
    `provider` String,
    `region` String,
    `ipaddr` IPv4,
    `ipv6addr` IPv6,
    `draining_at` Nullable(DateTime(\'UTC\')),
    `sign` Int8,
    `destroyed_at` Nullable(DateTime(\'UTC\'))
)
ENGINE = CollapsingMergeTree(sign)
ORDER BY name
SETTINGS index_granularity = 8
```

#### url_priorities table

This table stores rules to compute priorities for URLs used in
[Web connectivity test](#web-connectivity-test)&thinsp;Ⓣ.

See [Prioritization](#prioritization)&thinsp;🐝,
[Prioritization management](#api:priomgm) and [Prioritization rules UI](#prioritization-rules-ui)&thinsp;🖱

Schema:

```sql
CREATE TABLE default.url_priorities
(
    `sign` Int8,
    `category_code` String,
    `cc` String,
    `domain` String,
    `url` String,
    `priority` Int32
)
ENGINE = CollapsingMergeTree(sign)
ORDER BY (category_code, cc, domain, url, priority)
SETTINGS index_granularity = 1024
```

### ClickHouse system tables

ClickHouse has many system tables that can be used for monitoring
performance and debugging.

Tables matching the following names (wildcard) can grow in size and also
cause unnecessary I/O load:

    system.asynchronous_metric_log*
    system.metric_log*
    system.query_log*
    system.query_thread_log*
    system.trace_log*

#### Fastpath deduplication

ClickHouse does not deduplicate all records deterministically for
performance reasons. Full deduplication can be performed with the
following command and it is often required after running the fastpath to
reprocess old measurements. Deduplication is CPU and IO-intensive.

    time clickhouse-client -u admin --password admin --receive_timeout 9999 --send_timeout 9999 --query 'OPTIMIZE TABLE fastpath FINAL'

#### Dropping tables

ClickHouse has a protection against table drops. Use this to allow
dropping a table once. After use the flag file is automatically removed:

    sudo touch '/var/lib/clickhouse/flags/force_drop_table' && sudo chmod 666 '/var/lib/clickhouse/flags/force_drop_table'

#### Investigating table sizes

To monitor ClickHouse's performance and table size growth there's a
[dashboard](#dash:clickhouse) and the [ClickHouse queries notebook](#clickhouse-queries-notebook)&thinsp;📔

To investigate table and index sizes the following query is useful:

```sql
SELECT
    concat(database, '.', table) AS table,
    formatReadableSize(sum(bytes)) AS size,
    sum(rows) AS rows,
    max(modification_time) AS latest_modification,
    sum(bytes) AS bytes_size,
    any(engine) AS engine,
    formatReadableSize(sum(primary_key_bytes_in_memory)) AS primary_keys_size
FROM system.parts
WHERE active
GROUP BY database, table
ORDER BY bytes_size DESC
```

> **important**
> The system tables named `asynchronous_metric_log`, `query_log` and
> `query_thread_log` can be useful for debugging and performance
> optimization but grow over time and create additional I/O traffic. Also
> see [ClickHouse system tables](#clickhouse-system-tables)&thinsp;💡.

Possible workarounds are:

- Drop old records.

- Implement sampling writes that write only a percentage of the
  records.

- Disable logging for specific users or queries.

- Disable logging in the codebase running the query. See
  <https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/fastpath/fastpath/db.py#L177>
  for an example of custom settings.

- Disable logging altogether.

Also see [Disable unnecessary ClickHouse system tables](#disable-unnecessary-clickhouse-system-tables)&thinsp;🐞

#### Investigating database performance

If needed a simple script can be run to generate additional metrics and
logs to identify slow queries.

```bash
while true;
do
  # Extract longest running query time and send it as a statsd metric
  v=$(clickhouse-client -q 'SELECT elapsed FROM system.processes ORDER BY elapsed DESC LIMIT 1')
  echo "clickhouse_longest_query_elapsed_seconds:$v|g" | nc -w 1 -u 127.0.0.1 8125

  # Extract count of running queries and send it as a statsd metric
  v=$(clickhouse-client -q 'SELECT count() FROM system.processes')
  echo "clickhouse_running_queries_count:$v|g" | nc -w 1 -u 127.0.0.1 8125

  # Log long running queries into journald
  clickhouse-client -q 'SELECT query FROM system.processes WHERE elapsed > 10' | sed 's/\\n//g' | systemd-cat -t click-queries

  sleep 1
done
```

### Continuous Deployment: Database schema changes

The database schema required by the API is stored in
<https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/api/tests/integ/clickhouse_1_schema.sql>

In a typical CD workflows it is possible to deploy database schema
changes in a way that provides safety against outages and requires no
downtimes.

Any component that can be deployed independently from others can be made
responsible for creating and updating the tables it needs. If multiple
components access the same table it's important to coordinate their code
updates and deployments during schema changes.

> **important**
> typical CD requires deployments to be performed incrementally to speed
> up and simplify rollouts. It does not guarantees that package versions
> can be rolled forward or back by skipping intermediate versions.

To support such use-case more complex database scheme versioning would
be required. Due to hardware resource constraints and time constraints
we need to be able to manually create new tables (especially on the test
stage) and perform analysis work, run performance and feature tests,
troubleshooting etc. As such, at this time the backend components are
not checking the database schema against a stored \"template\" at
install or start time.

> **note**
> A starting point for more automated database versioning existed at
> <https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/api/database_upgrade_schema.py>

> **note**
> in future such check could be implemented and generate a warning to be
> enabled only on non-test CD stages.

> **note**
> one way to make database changes at package install time is to use the
> `debian/postinst` script. For example see
> <https://github.com/ooni/backend/blob/0ec9fba0eb9c4c440dcb7456f2aab529561104ae/fastpath/debian/postinst>

> **important**
> in writing SQL queries explicitly set the columns you need to read or
> write and access them by name: any new column will be ignored.

Some examples of database schema change workflows:

#### Adding a new column to the fastpath

The following workflow can be tweaked or simplified to add columns or
tables to other components.

> **note**
> multiple deployments or restarts should not trigger failures: always add
> columns using
> `ALTER TABLE <name> ADD COLUMN IF NOT EXISTS <name> <other parameters>`

The new column is added either manually or by deploying a new version of
the fastpath package that adds the column at install or start time.
Ensure the rollout reaches all the CD stages.

Prepare, code-review, merge and deploy a new version of the fastpath
that writes data to the new column. Ensure the rollout reaches all the
CD stages.

Verify the contents of the new column e.g. using a Jupyter Notebook

Prepare, code-review, merge and deploy a new version of the API that
reads data from the new column. Ensure the rollout reaches all the CD
stages.

This workflow guarantees that the same schema and codebase has been
tested on all stages before reaching production.

#### Renaming a column or table

This is a more complex workflow especially when multiple components
access the same table or column. It can also be used for changing a
column type and other invasive changes.

For each of the following steps ensure the rollout reaches all the CD
stages.

- Create a new column or table.

- Prepare, code-review, merge and deploy a new version of all the
  components that write data. Write all data to both the old and new
  column/table.

- If required, run one-off queries that migrate existing data from the
  old column/table to the new one. Using `IF NOT EXISTS` can be
  useful.

- Prepare, code-review, merge and deploy a new version of all the
  components that reads data. Update queries to only read from the new
  column/table.

- Prepare, code-review, merge and deploy a new version of all the
  components that write data. Write data only to the new column/table.

- Run one-off queries to delete the old column/table. Using
  `IF EXISTS` can be useful for idempotent runs.

#### Database schema check

To compare the database schemas across backend hosts you can use:

```bash
for hn in ams-pg-test backend-hel backend-fsn; do
  hn=${hn}.ooni.org
  echo $hn
  > "schema_${hn}"
  for tbl in $(ssh $hn 'clickhouse-client -q "SHOW TABLES FROM default"' | grep -v inner_id ); do
    echo "  ${tbl}"
    ssh $hn "clickhouse-client -q \"SHOW CREATE TABLE default.${tbl}\"" | sed 's/\\n/\n/g' >> "schema_${hn}"
  done
done
```

The generated files can be compared more easily using `meld`.

Also related: [Database backup tool](#database-backup-tool)&thinsp;⚙
