BEGIN;
SELECT
    _v.unregister_patch ('021-counters-table');
DROP TABLE fastpath;
COMMIT;

