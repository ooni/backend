-- Create counters btree index
-- Formatted with pgformatter 3.3

BEGIN;
SELECT
    _v.register_patch ( '024-create-counters-btree-idx', ARRAY['023-grant-select-counters-amsapi'], NULL);

CREATE INDEX measurement_start_day_btree_idx ON counters (measurement_start_day);

COMMIT;
