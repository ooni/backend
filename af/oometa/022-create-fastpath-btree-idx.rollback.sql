BEGIN;
SELECT
    _v.unregister_patch ('022-create-fastpath-btree-idx');
DROP INDEX measurement_start_time_btree_idx
COMMIT;
