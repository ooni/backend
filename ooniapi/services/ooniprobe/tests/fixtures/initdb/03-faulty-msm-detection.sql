-- Context: https://github.com/ooni/backend/issues/1070
-- The following tables support the collection of faulty measurements analytics

CREATE TABLE IF NOT EXISTS default.geoip_mismatch
(
    `measurement_uid` String,
    `time` DateTime DEFAULT now(),
    -- reported by the probe
    `probe_cc` String,
    `probe_asn` UInt32,
    -- geoip lookup result
    `actual_cc` String,
    `actual_asn` UInt32
)
ENGINE = ReplacingMergeTree
ORDER BY (measurement_uid)
SETTINGS
    -- These settings will buffer inserts and return without verifying that they reached disk
    -- See: https://clickhouse.com/docs/best-practices/selecting-an-insert-strategy#asynchronous-inserts
    async_insert=1,
    wait_for_async_insert=0;
