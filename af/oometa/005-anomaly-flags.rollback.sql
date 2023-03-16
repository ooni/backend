BEGIN;

select _v.unregister_patch( '005-anomaly-flags' );

ALTER TABLE measurement DROP COLUMN confirmed, DROP COLUMN anomaly, DROP COLUMN msm_failure;
DROP TABLE label;

COMMIT;
