#!/usr/bin/env python3
"""
Roll-forward / rollback database schemas

Can be used from CLI and as a Python module
"""

from argparse import ArgumentParser
import logging

from clickhouse_driver import Client as Clickhouse

log = logging.getLogger("database_upgrade_schema")


def run(sql):
    title = sql.split("(")[0].strip()
    log.info(f"Running query {title}")
    click = Clickhouse(host="localhost")
    click.execute(sql)


def setup_db():
    """Setup database from scratch"""
    # Main tables
    run(
        """
CREATE TABLE IF NOT EXISTS default.fastpath
(
    `measurement_uid` String,
    `report_id` String,
    `input` String,
    `probe_cc` String,
    `probe_asn` Int32,
    `test_name` String,
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
    `server_as_name` String
)
ENGINE = ReplacingMergeTree
ORDER BY (measurement_start_time, report_id, input)
SETTINGS index_granularity = 8192"""
    )
    run(
        """
CREATE TABLE IF NOT EXISTS default.jsonl
(
    `report_id` String,
    `input` String,
    `s3path` String,
    `linenum` Int32,
    `measurement_uid` String
)
ENGINE = MergeTree
ORDER BY (report_id, input)
SETTINGS index_granularity = 8192"""
    )
    run(
        """
CREATE TABLE IF NOT EXISTS default.url_priorities (
    `category_code` String,
    `cc` String,
    `domain` String,
    `url` String,
    `priority` Int32
)
ENGINE = ReplacingMergeTree
ORDER BY (category_code, cc, domain, url)
SETTINGS index_granularity = 8192"""
    )
    run(
        """
CREATE TABLE IF NOT EXISTS default.citizenlab
(
    `domain` String,
    `url` String,
    `cc` FixedString(32),
    `category_code` String
)
ENGINE = ReplacingMergeTree
ORDER BY (domain, url, cc, category_code)
SETTINGS index_granularity = 4"""
    )
    run(
        """
CREATE TABLE IF NOT EXISTS default.citizenlab_flip AS default.citizenlab"""
    )
    run(
        """
CREATE TABLE IF NOT EXISTS test_groups (
  `test_name` String,
  `test_group` String
)
ENGINE = Join(ANY, LEFT, test_name)"""
    )
    run(
        """
-- Auth

CREATE TABLE IF NOT EXISTS accounts
(
    `account_id` FixedString(32),
    `role` String
)
ENGINE = EmbeddedRocksDB
PRIMARY KEY account_id"""
    )
    run(
        """
CREATE TABLE IF NOT EXISTS session_expunge
(
    `account_id` FixedString(32),
    `threshold` DateTime DEFAULT now()
)
ENGINE = EmbeddedRocksDB
PRIMARY KEY account_id"""
    )

    # Materialized views
    run(
        """
CREATE MATERIALIZED VIEW IF NOT EXISTS default.counters_test_list
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
WHERE (measurement_start_time < now()) AND (measurement_start_time > (now() - toIntervalDay(8))) AND (test_name = 'web_connectivity')
GROUP BY
    day,
    probe_cc,
    input"""
    )

    run(
        """
CREATE MATERIALIZED VIEW IF NOT EXISTS default.counters_asn_test_list
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
WHERE (measurement_start_time < now()) AND (measurement_start_time > (now() - toIntervalDay(8))) AND (test_name = 'web_connectivity')
GROUP BY
    week,
    probe_cc,
    probe_asn,
    input"""
    )


if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("--upgrade", action="store_true")
    conf = ap.parse_args()
    if conf.upgrade:
        setup_db()
