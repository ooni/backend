BEGIN;

select _v.register_patch( '004-measurements-index', ARRAY[ '003-msm-index' ], NULL );

-- Everything goes to `public` schema.

-- Almost blind copy-paste from https://github.com/TheTorProject/ooni-measurements/pull/22#issue-236675611
CREATE INDEX measurement_report_no_idx ON measurement (report_no);
CREATE INDEX measurement_input_no_idx ON measurement (input_no);
CREATE INDEX measurement_id_idx ON measurement (id);
CREATE INDEX report_autoclaved_no_idx ON report (autoclaved_no);

COMMIT;
