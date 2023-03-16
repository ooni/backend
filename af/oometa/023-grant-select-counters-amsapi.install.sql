-- Grant SELECT on counters to amsapi

BEGIN;
SELECT
    _v.register_patch ( '023-grant-select-counters-amsapi', ARRAY['022-create-fastpath-btree-idx'], NULL);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'amsapi') THEN
        GRANT SELECT ON counters TO amsapi;
    END IF;
END
$$;

COMMIT;
