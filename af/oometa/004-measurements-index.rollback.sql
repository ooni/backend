BEGIN;

select _v.unregister_patch( '004-measurements-index' );

DROP INDEX measurement_report_no_idx;
DROP INDEX measurement_input_no_idx;
DROP INDEX measurement_id_idx;
DROP INDEX report_autoclaved_no_idx;

COMMIT;
