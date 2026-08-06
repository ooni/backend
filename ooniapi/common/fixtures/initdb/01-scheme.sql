-- Create tables for Clickhouse integ tests

-- Main tables

CREATE TABLE default.fastpath
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
    `architecture` String,
    `engine_name` String,
    `engine_version` String,
    `test_runtime` Float32,
    `blocking_type` String,
    `test_helper_address` LowCardinality(String),
    `test_helper_type` LowCardinality(String),
    `ooni_run_link_id` Nullable(UInt64),
    `is_verified` LowCardinality(String) DEFAULT 'u'
)
ENGINE = ReplacingMergeTree
ORDER BY (measurement_start_time, report_id, input)
SETTINGS index_granularity = 8192;

CREATE TABLE default.jsonl
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

CREATE TABLE default.url_priorities (
    `sign` Int8,
    `category_code` String,
    `cc` String,
    `domain` String,
    `url` String,
    `priority` Int32
)
ENGINE = CollapsingMergeTree(sign)
ORDER BY (category_code, cc, domain, url, priority)
SETTINGS index_granularity = 1024;

CREATE TABLE default.citizenlab
(
    `domain` String,
    `url` String,
    `cc` FixedString(32),
    `category_code` String
)
ENGINE = ReplacingMergeTree
ORDER BY (domain, url, cc, category_code)
SETTINGS index_granularity = 4;

CREATE TABLE default.citizenlab_flip AS default.citizenlab;

CREATE TABLE test_groups (
  `test_name` String,
  `test_group` String
)
ENGINE = Join(ANY, LEFT, test_name);


-- Auth

CREATE TABLE accounts
(
    `account_id` FixedString(32),
    `role` String
)
ENGINE = EmbeddedRocksDB
PRIMARY KEY account_id;

-- Materialized views

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
WHERE (measurement_start_time < now()) AND (measurement_start_time > (now() - toIntervalDay(8))) AND (test_name = 'web_connectivity')
GROUP BY
    day,
    probe_cc,
    input;

CREATE MATERIALIZED VIEW default.counters_asn_test_list
(
    `week` DateTime,
    `probe_cc` String,
    `probe_asn` UInt32,
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
    input;

CREATE TABLE msmt_feedback
(
    `measurement_uid` String,
    `account_id` String,
    `status` String,
    `update_time` DateTime64(3) MATERIALIZED now64()
)
ENGINE = ReplacingMergeTree
ORDER BY (measurement_uid, account_id)
SETTINGS index_granularity = 4;

CREATE TABLE default.fingerprints_dns
(
    `name` String,
    `scope` Enum8('nat' = 1, 'isp' = 2, 'prod' = 3, 'inst' = 4, 'vbw' = 5, 'fp' = 6),
    `other_names` String,
    `location_found` String,
    `pattern_type` Enum8('full' = 1, 'prefix' = 2, 'contains' = 3, 'regexp' = 4),
    `pattern` String,
    `confidence_no_fp` UInt8,
    `expected_countries` String,
    `source` String,
    `exp_url` String,
    `notes` String
)
ENGINE = EmbeddedRocksDB
PRIMARY KEY name;

CREATE TABLE default.fingerprints_http
(
    `name` String,
    `scope` Enum8('nat' = 1, 'isp' = 2, 'prod' = 3, 'inst' = 4, 'vbw' = 5, 'fp' = 6, 'injb' = 7, 'prov' = 8),
    `other_names` String,
    `location_found` String,
    `pattern_type` Enum8('full' = 1, 'prefix' = 2, 'contains' = 3, 'regexp' = 4),
    `pattern` String,
    `confidence_no_fp` UInt8,
    `expected_countries` String,
    `source` String,
    `exp_url` String,
    `notes` String
)
ENGINE = EmbeddedRocksDB
PRIMARY KEY name;

CREATE TABLE asnmeta
(
    `asn` UInt32,
    `org_name` String,
    `cc` String,
    `changed` Date,
    `aut_name` String,
    `source` String
)
ENGINE = MergeTree
ORDER BY (asn, changed);

CREATE TABLE IF NOT EXISTS default.incidents
(
    `update_time` DateTime DEFAULT now(),
    `create_time` DateTime DEFAULT now(),
    `start_time` DateTime DEFAULT now(),
    `end_time` Nullable(DateTime),
    `creator_account_id` FixedString(32),
    `reported_by` String,
    `email_address` String,
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
)
ENGINE = ReplacingMergeTree(update_time)
ORDER BY (id)
SETTINGS index_granularity = 1;

CREATE TABLE IF NOT EXISTS default.oonirun
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
SETTINGS index_granularity = 1;

CREATE TABLE
    analysis_web_measurement (
        `domain` String,
        `input` String,
        `test_name` String,
        `probe_asn` UInt32,
        `probe_as_org_name` String,
        `probe_cc` String,
        `resolver_asn` UInt32,
        `resolver_as_cc` String,
        `network_type` String,
        `measurement_start_time` DateTime64 (3, 'UTC'),
        `measurement_uid` String,
        `ooni_run_link_id` String,
        `top_probe_analysis` Nullable (String),
        `top_dns_failure` Nullable (String),
        `top_tcp_failure` Nullable (String),
        `top_tls_failure` Nullable (String),
        `dns_blocked` Float32,
        `dns_down` Float32,
        `dns_ok` Float32,
        `tcp_blocked` Float32,
        `tcp_down` Float32,
        `tcp_ok` Float32,
        `tls_blocked` Float32,
        `tls_down` Float32,
        `tls_ok` Float32
    ) ENGINE = ReplacingMergeTree PRIMARY KEY measurement_uid
ORDER BY
    (
        measurement_uid,
        measurement_start_time,
        probe_cc,
        probe_asn
    ) SETTINGS index_granularity = 8192;

CREATE TABLE
    obs_web (
        `measurement_uid` String,
        `observation_idx` UInt16,
        `input` Nullable (String),
        `report_id` String,
        `ooni_run_link_id` String DEFAULT '',
        `measurement_start_time` DateTime64 (3, 'UTC'),
        `software_name` String,
        `software_version` String,
        `test_name` String,
        `test_version` String,
        `bucket_date` String,
        `probe_asn` UInt32,
        `probe_cc` String,
        `probe_as_org_name` String,
        `probe_as_cc` String,
        `probe_as_name` String,
        `network_type` String,
        `platform` String,
        `origin` String,
        `engine_name` String,
        `engine_version` String,
        `architecture` String,
        `resolver_ip` String,
        `resolver_asn` UInt32,
        `resolver_cc` String,
        `resolver_as_org_name` String,
        `resolver_as_cc` String,
        `resolver_is_scrubbed` UInt8,
        `resolver_asn_probe` UInt32,
        `resolver_as_org_name_probe` String,
        `created_at` Nullable (DateTime ('UTC')),
        `target_id` Nullable (String),
        `hostname` Nullable (String),
        `transaction_id` Nullable (UInt16),
        `ip` Nullable (String),
        `port` Nullable (UInt16),
        `ip_asn` Nullable (UInt32),
        `ip_as_org_name` Nullable (String),
        `ip_as_cc` Nullable (String),
        `ip_cc` Nullable (String),
        `ip_is_bogon` Nullable (UInt8),
        `dns_query_type` Nullable (String),
        `dns_failure` Nullable (String),
        `dns_engine` Nullable (String),
        `dns_engine_resolver_address` Nullable (String),
        `dns_answer_type` Nullable (String),
        `dns_answer` Nullable (String),
        `dns_answer_asn` Nullable (UInt32),
        `dns_answer_as_org_name` Nullable (String),
        `dns_t` Nullable (Float64),
        `tcp_failure` Nullable (String),
        `tcp_success` Nullable (UInt8),
        `tcp_t` Nullable (Float64),
        `tls_failure` Nullable (String),
        `tls_server_name` Nullable (String),
        `tls_outer_server_name` Nullable (String),
        `tls_echconfig` Nullable (String),
        `tls_version` Nullable (String),
        `tls_cipher_suite` Nullable (String),
        `tls_is_certificate_valid` Nullable (UInt8),
        `tls_end_entity_certificate_fingerprint` Nullable (String),
        `tls_end_entity_certificate_subject` Nullable (String),
        `tls_end_entity_certificate_subject_common_name` Nullable (String),
        `tls_end_entity_certificate_issuer` Nullable (String),
        `tls_end_entity_certificate_issuer_common_name` Nullable (String),
        `tls_end_entity_certificate_san_list` Array (String),
        `tls_end_entity_certificate_not_valid_after` Nullable (DateTime64 (3, 'UTC')),
        `tls_end_entity_certificate_not_valid_before` Nullable (DateTime64 (3, 'UTC')),
        `tls_certificate_chain_length` Nullable (UInt16),
        `tls_certificate_chain_fingerprints` Array (String),
        `tls_handshake_read_count` Nullable (UInt16),
        `tls_handshake_write_count` Nullable (UInt16),
        `tls_handshake_read_bytes` Nullable (UInt32),
        `tls_handshake_write_bytes` Nullable (UInt32),
        `tls_handshake_last_operation` Nullable (String),
        `tls_handshake_time` Nullable (Float64),
        `tls_t` Nullable (Float64),
        `http_request_url` Nullable (String),
        `http_network` Nullable (String),
        `http_alpn` Nullable (String),
        `http_failure` Nullable (String),
        `http_request_body_length` Nullable (UInt32),
        `http_request_method` Nullable (String),
        `http_runtime` Nullable (Float64),
        `http_response_body_length` Nullable (Int32),
        `http_response_body_is_truncated` Nullable (UInt8),
        `http_response_body_sha1` Nullable (String),
        `http_response_status_code` Nullable (UInt16),
        `http_response_header_location` Nullable (String),
        `http_response_header_server` Nullable (String),
        `http_request_redirect_from` Nullable (String),
        `http_request_body_is_truncated` Nullable (UInt8),
        `http_t` Nullable (Float64),
        `probe_analysis` Nullable (String)
    ) ENGINE = ReplacingMergeTree PRIMARY KEY (measurement_uid, observation_idx)
ORDER BY
    (
        measurement_uid,
        observation_idx,
        measurement_start_time,
        probe_cc,
        probe_asn
    ) SETTINGS index_granularity = 8192;
