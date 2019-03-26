BEGIN;

select _v.unregister_patch( '013-ooexpl-website-table');

DROP TABLE ooexpl_website_msm;

COMMIT;
