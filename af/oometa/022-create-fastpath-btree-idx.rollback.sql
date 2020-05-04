BEGIN;
SELECT
    _v.unregister_patch ('021-counters-table');
DROP INDEX measurement_start_time_btree_idx
COMMIT;
