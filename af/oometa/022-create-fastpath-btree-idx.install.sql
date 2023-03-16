-- Create fastpath btree index
-- Formatted with pgformatter 3.3

BEGIN;
SELECT
    _v.register_patch ( '022-create-fastpath-btree-idx', ARRAY['021-counters-table'], NULL);

CREATE INDEX measurement_start_time_btree_idx ON fastpath (measurement_start_time);

COMMIT;
