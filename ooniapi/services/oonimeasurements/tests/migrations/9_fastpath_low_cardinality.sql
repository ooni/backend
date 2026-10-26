-- anomaly, confirmed and msm_failure are now LowCardinality in production,
-- like probe_cc, test_name and engine_name

ALTER TABLE default.fastpath
    MODIFY COLUMN anomaly LowCardinality(String),
    MODIFY COLUMN confirmed LowCardinality(String),
    MODIFY COLUMN msm_failure LowCardinality(String)
SETTINGS mutations_sync = 1
