-- analysis_web_measurement is sorted by measurement_uid; see
-- 6_obs_web_measurement_start_time_idx.sql. ooni/devops benchmark.sql shows
-- this index may already exist in production, in which case this is a no-op.
--
-- Production (ooni/devops schema.sql):
--   ALTER TABLE ooni.analysis_web_measurement ON CLUSTER oonidata_cluster ADD INDEX IF NOT EXISTS measurement_start_time_idx measurement_start_time TYPE minmax GRANULARITY 1;
--   ALTER TABLE ooni.analysis_web_measurement ON CLUSTER oonidata_cluster MATERIALIZE INDEX measurement_start_time_idx;

ALTER TABLE default.analysis_web_measurement ADD INDEX IF NOT EXISTS measurement_start_time_idx measurement_start_time TYPE minmax GRANULARITY 1;

ALTER TABLE default.analysis_web_measurement MATERIALIZE INDEX measurement_start_time_idx SETTINGS mutations_sync = 1
