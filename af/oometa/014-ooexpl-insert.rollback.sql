BEGIN;

select _v.unregister_patch( '014-ooexpl-insert');

TRUNCATE ooexpl_bucket_msm_count, ooexpl_daily_msm_count;

COMMIT;
