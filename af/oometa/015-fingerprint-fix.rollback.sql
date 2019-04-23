BEGIN;

select _v.unregister_patch( '015-fingerprint-fix');

UPDATE fingerprint
SET "origin_cc"='UK' WHERE "origin_cc"='GB';

COMMIT;
