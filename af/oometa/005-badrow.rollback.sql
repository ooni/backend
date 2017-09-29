BEGIN;

select _v.unregister_patch( '005-badrow' );

DROP TABLE badrow;

COMMIT;
