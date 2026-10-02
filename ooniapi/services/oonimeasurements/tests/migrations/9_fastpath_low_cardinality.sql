-- anomaly, confirmed and msm_failure hold 't' or 'f', probe_cc a country code
-- and test_name one of a few dozen names. As String each costs its bytes plus
-- an 8 byte offset per row; LowCardinality stores a small index into a
-- dictionary instead, so aggregations, which read these columns for every
-- measurement in their window, read 5-7x fewer bytes. Values, query results
-- and inserts are unchanged: LowCardinality(String) behaves as String.
--
-- Production (ooni/devops schema.sql). Each statement is a mutation that
-- rewrites one column of every part on every replica, so run them off-peak,
-- one at a time, and follow system.mutations:
--   ALTER TABLE ooni.fastpath ON CLUSTER oonidata_cluster MODIFY COLUMN anomaly LowCardinality(String);
--   ALTER TABLE ooni.fastpath ON CLUSTER oonidata_cluster MODIFY COLUMN confirmed LowCardinality(String);
--   ALTER TABLE ooni.fastpath ON CLUSTER oonidata_cluster MODIFY COLUMN msm_failure LowCardinality(String);
--   ALTER TABLE ooni.fastpath ON CLUSTER oonidata_cluster MODIFY COLUMN probe_cc LowCardinality(String);
--   ALTER TABLE ooni.fastpath ON CLUSTER oonidata_cluster MODIFY COLUMN test_name LowCardinality(String);

ALTER TABLE default.fastpath
    MODIFY COLUMN anomaly LowCardinality(String),
    MODIFY COLUMN confirmed LowCardinality(String),
    MODIFY COLUMN msm_failure LowCardinality(String),
    MODIFY COLUMN probe_cc LowCardinality(String),
    MODIFY COLUMN test_name LowCardinality(String)
SETTINGS mutations_sync = 1
