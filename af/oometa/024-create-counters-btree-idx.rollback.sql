
BEGIN;
SELECT
    _v.unregister_patch ('024-create-counters-btree-idx');
DROP INDEX measurement_start_time_btree_idx
COMMIT;
