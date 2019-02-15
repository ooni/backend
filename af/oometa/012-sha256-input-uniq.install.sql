BEGIN;

select _v.register_patch( '012-sha256-input-uniq', ARRAY[ '011-cleanup' ], NULL );

-- ERROR: index row size 6512 exceeds maximum 2712 for index "input_input_key"
-- See https://github.com/ooni/pipeline/issues/139 for details.

-- pgcrypto is already loaded
alter table input drop constraint input_input_key;
create unique index input_input_sha256_key on input (digest(input::text, 'sha256'));

COMMIT;
