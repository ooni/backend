BEGIN;

select _v.register_patch( '015-fingerprint-fix', ARRAY[ '014-ooexpl-insert' ], NULL );

UPDATE fingerprint
SET "origin_cc"='GB' WHERE "origin_cc"='UK';

COMMIT;
