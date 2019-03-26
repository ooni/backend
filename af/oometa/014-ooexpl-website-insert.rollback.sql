BEGIN;

select _v.unregister_patch( '014-ooexpl-website-insert');

TRUNCATE ooexpl_website_msm;

COMMIT;
