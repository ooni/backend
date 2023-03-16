-- Add confirmed and anomaly columns to fastpath table
-- Formatted with pgformatter 3.3

BEGIN;
SELECT
    _v.register_patch ('019-fastpath-confirmed',
        ARRAY['018-fastpath'],
        NULL);
ALTER TABLE fastpath
    ADD COLUMN anomaly boolean,
    ADD COLUMN confirmed boolean,
    ADD COLUMN msm_failure boolean;

-- Switch to BRIN index for measurement_start_time
DROP INDEX measurement_start_time_idx;
CREATE INDEX fastpath_measurement_start_time_idx ON fastpath
USING BRIN (measurement_start_time) WITH (pages_per_range = 128);

-- Rename indexes
ALTER INDEX input_idx RENAME TO fastpath_input_idx;
ALTER INDEX report_id_idx RENAME TO fastpath_report_id_idx;

COMMIT;

