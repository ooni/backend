BEGIN;
SELECT
    _v.unregister_patch ('023-grant-select-counters-amsapi');

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'amsapi') THEN
        REVOKE SELECT ON counters FROM amsapi;
    END IF;
END
$$;

COMMIT;
