-- report_id starts with the test start time, so like fastpath_rid_idx on
-- fastpath, min/max bounds per granule prune lookups by report_id.
--
-- Production (ooni/devops schema.sql):
--   ALTER TABLE ooni.obs_web ON CLUSTER oonidata_cluster ADD INDEX IF NOT EXISTS report_id_idx report_id TYPE minmax GRANULARITY 1;
--   ALTER TABLE ooni.obs_web ON CLUSTER oonidata_cluster MATERIALIZE INDEX report_id_idx;

ALTER TABLE default.obs_web ADD INDEX IF NOT EXISTS report_id_idx report_id TYPE minmax GRANULARITY 1;

ALTER TABLE default.obs_web MATERIALIZE INDEX report_id_idx SETTINGS mutations_sync = 1
