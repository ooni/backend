-- Create tables for Clickhouse integ tests

CREATE TABLE IF NOT EXISTS default.fastpath
(
    `measurement_uid` String,
    `report_id` String,
    `input` String,
    `probe_cc` String,
    `probe_asn` UInt32,
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
    `server_as_name` String,
    `update_time` DateTime64(3) MATERIALIZED now64(),
    `test_version` String,
    `test_runtime` Float32,
    `architecture` String,
    `engine_name` String,
    `engine_version` String,
    `blocking_type` String,
    `test_helper_address` LowCardinality(String),
    `test_helper_type` LowCardinality(String),
    `ooni_run_link_id` Nullable(UInt64)
)
ENGINE = ReplacingMergeTree
ORDER BY (measurement_start_time, report_id, input)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS default.citizenlab
(
    `domain` String,
    `url` String,
    `cc` FixedString(32),
    `category_code` String
)
ENGINE = ReplacingMergeTree
ORDER BY (domain, url, cc, category_code)
SETTINGS index_granularity = 4;

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
SETTINGS index_granularity = 8192;

ALTER TABLE default.fastpath ADD COLUMN IF NOT EXISTS `is_verified` Int8;
ALTER TABLE default.fastpath ADD COLUMN IF NOT EXISTS `nym` Nullable(String);
ALTER TABLE default.fastpath ADD COLUMN IF NOT EXISTS `zkp_request` Nullable(String);
ALTER TABLE default.fastpath ADD COLUMN IF NOT EXISTS `age_range` Nullable(String);
ALTER TABLE default.fastpath ADD COLUMN IF NOT EXISTS `msm_range` Nullable(String);
