BEGIN;

select _v.register_patch( '005-badrow', ARRAY[ '004-measurements-index' ], NULL );

-- Everything goes to `public` schema.
CREATE TABLE badrow (
    tbl text NOT NULL,
    code_ver integer NOT NULL,
    datum bytea NOT NULL);

COMMIT;
