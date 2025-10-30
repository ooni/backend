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

CREATE TABLE IF NOT EXISTS default.event_detector_changepoints
(
    `probe_asn` UInt32,
    `probe_cc` String,
    `domain` String,
    `ts` DateTime64(3, 'UTC'),
    `count_isp_resolver` Nullable(UInt32),
    `count_other_resolver` Nullable(UInt32),
    `count` Nullable(UInt32),
    `dns_isp_blocked` Nullable(Float32),
    `dns_other_blocked` Nullable(Float32),
    `tcp_blocked` Nullable(Float32),
    `tls_blocked` Nullable(Float32),
    `last_ts` DateTime64(3, 'UTC'),
    `dns_isp_blocked_obs_w_sum` Nullable(Float32),
    `dns_isp_blocked_w_sum` Nullable(Float32),
    `dns_isp_blocked_s_pos` Nullable(Float32),
    `dns_isp_blocked_s_neg` Nullable(Float32),
    `dns_other_blocked_obs_w_sum` Nullable(Float32),
    `dns_other_blocked_w_sum` Nullable(Float32),
    `dns_other_blocked_s_pos` Nullable(Float32),
    `dns_other_blocked_s_neg` Nullable(Float32),
    `tcp_blocked_obs_w_sum` Nullable(Float32),
    `tcp_blocked_w_sum` Nullable(Float32),
    `tcp_blocked_s_pos` Nullable(Float32),
    `tcp_blocked_s_neg` Nullable(Float32),
    `tls_blocked_obs_w_sum` Nullable(Float32),
    `tls_blocked_w_sum` Nullable(Float32),
    `tls_blocked_s_pos` Nullable(Float32),
    `tls_blocked_s_neg` Nullable(Float32),
    `change_dir` Nullable(Int8),
    `s_pos` Nullable(Float32),
    `s_neg` Nullable(Float32),
    `current_mean` Nullable(Float32),
    `h` Nullable(Float32)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(ts)
ORDER BY (probe_asn, probe_cc, ts, domain)
SETTINGS index_granularity = 8192;