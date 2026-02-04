-- Context: https://github.com/ooni/backend/issues/1070
-- The following tables support the collection of faulty measurements analytics

CREATE TABLE IF NOT EXISTS default.geoip_mismatch
(
    `measurement_uid` String,
    -- reported by the probe
    `probe_cc` String,
    `probe_asn` UInt32,
    -- geoip lookup result
    `actual_cc` String,
    `actual_asn` UInt32
)
ENGINE = ReplacingMergeTree
ORDER BY (measurement_uid);
