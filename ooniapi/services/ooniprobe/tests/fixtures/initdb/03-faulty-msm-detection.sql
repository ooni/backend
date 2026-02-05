-- Context: https://github.com/ooni/backend/issues/1070
-- The following tables support the collection of faulty measurements analytics

CREATE TABLE IF NOT EXISTS default.faulty_measurements
(
    `measurement_uid` String,
    `time` DateTime DEFAULT now(),
    `type` String,
    -- geoip lookup result for the probe IP
    `probe_cc` String,
    `probe_asn` UInt32,
    -- JSON-encoded details about the anomaly
    `details` String
)
ENGINE = ReplacingMergeTree
ORDER BY (measurement_uid)
SETTINGS
    -- These settings will buffer inserts and return without verifying that they reached disk
    -- See: https://clickhouse.com/docs/best-practices/selecting-an-insert-strategy#asynchronous-inserts
    async_insert=1,
    wait_for_async_insert=0;
