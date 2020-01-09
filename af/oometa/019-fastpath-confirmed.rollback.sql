-- Remove confirmed and anomaly columns to fastpath table
-- Formatted with pgformatter 3.3

BEGIN;
SELECT
    _v.unregister_patch ('019-fastpath-confirmed');
ALTER TABLE fastpath
    DROP COLUMN anomaly,
    DROP COLUMN confirmed,
    DROP COLUMN msm_failure;

DROP INDEX fastpath_measurement_start_time_idx;
CREATE INDEX measurement_start_time_idx ON fastpath (measurement_start_time);
ALTER INDEX fastpath_input_idx RENAME TO input_idx;
ALTER INDEX fastpath_report_id_idx RENAME TO report_id_idx;
COMMIT;

