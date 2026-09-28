-- Skip indexes that production fastpath already has (ooni/devops schema.sql),
-- so that tests and benchmarks run against the same access paths.

ALTER TABLE default.fastpath ADD INDEX IF NOT EXISTS fastpath_rid_idx report_id TYPE minmax GRANULARITY 1;

ALTER TABLE default.fastpath ADD INDEX IF NOT EXISTS measurement_uid_idx measurement_uid TYPE minmax GRANULARITY 8;

ALTER TABLE default.fastpath MATERIALIZE INDEX fastpath_rid_idx SETTINGS mutations_sync = 1;

ALTER TABLE default.fastpath MATERIALIZE INDEX measurement_uid_idx SETTINGS mutations_sync = 1
