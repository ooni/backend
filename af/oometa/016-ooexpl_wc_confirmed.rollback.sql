BEGIN;

select _v.unregister_patch( '016-ooexpl_wc_confirmed');

DROP MATERIALIZED VIEW ooexpl_wc_confirmed

COMMIT;
