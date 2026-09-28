-- obs_web is sorted by measurement_uid, so time range filters cannot use the
-- primary key. The uid prefix is the collection time, which tracks
-- measurement_start_time closely, so per granule min/max bounds prune well.
--
-- Production (ooni/devops schema.sql):
--   ALTER TABLE ooni.obs_web ON CLUSTER oonidata_cluster ADD INDEX IF NOT EXISTS measurement_start_time_idx measurement_start_time TYPE minmax GRANULARITY 1;
--   ALTER TABLE ooni.obs_web ON CLUSTER oonidata_cluster MATERIALIZE INDEX measurement_start_time_idx;

ALTER TABLE default.obs_web ADD INDEX IF NOT EXISTS measurement_start_time_idx measurement_start_time TYPE minmax GRANULARITY 1;

ALTER TABLE default.obs_web MATERIALIZE INDEX measurement_start_time_idx SETTINGS mutations_sync = 1;
