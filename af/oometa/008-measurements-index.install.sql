BEGIN;

select _v.register_patch( '008-measurements-index',  ARRAY[ '007-test-name-hotfix' ], NULL );

CREATE INDEX measurement_measurement_start_time_idx ON measurement (measurement_start_time);

CREATE EXTENSION pg_trgm;

CREATE INDEX input_input_trgm_idx ON input USING GIST (input gist_trgm_ops);
CREATE INDEX report_test_start_time_idx ON report (test_start_time);

COMMIT;
