BEGIN;
SELECT
    _v.unregister_patch ('018-fastpath');
DROP TABLE fastpath;
COMMIT;

