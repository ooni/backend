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