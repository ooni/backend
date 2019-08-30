BEGIN;

select _v.unregister_patch( '017-ooexpl_wc_input_counts');

DROP TABLE ooexpl_wc_input_counts

COMMIT;
