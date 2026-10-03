-- Context: https://github.com/ooni/backend/issues/1070
-- The following tables support the collection of faulty measurements analytics

CREATE TABLE IF NOT EXISTS default.faulty_measurements
(
    `ts` DateTime64(3, 'UTC') DEFAULT now64(),
    `type` String,
    `uid` UUID DEFAULT generateUUIDv4(),
    -- geoip lookup result for the probe IP
    `probe_cc` String,
    `probe_asn` UInt32,
    -- JSON-encoded details about the anomaly
    `details` String
)
ENGINE = ReplacingMergeTree
ORDER BY (ts, type, probe_cc, probe_asn, uid)
-- Inserts are asynchronous: ooniprobe sets async_insert=1 and
-- wait_for_async_insert=0 on each INSERT (ooniprobe/utils.py), as production
-- doesn't set them on the table.
SETTINGS index_granularity = 8192;
