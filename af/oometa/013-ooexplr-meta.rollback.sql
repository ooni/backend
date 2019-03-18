BEGIN;

select _v.unregister_patch( '013-ooexplr-meta');

DROP TABLE ooexpl_recent_msm_count;
DROP TABLE ooexpl_bucket_msm_count;
DROP MATERIALIZED VIEW ooexpl_website_msmts;

COMMIT;
