BEGIN;

select _v.unregister_patch( '013-ooexpl-tables');

DROP TABLE ooexpl_bucket_msm_count;
DROP TABLE ooexpl_daily_msm_count;

COMMIT;
