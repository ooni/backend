BEGIN;

select _v.unregister_patch( '016-ooexpl_wc_confirmed');

DROP TABLE ooexpl_wc_confirmed;

COMMIT;
