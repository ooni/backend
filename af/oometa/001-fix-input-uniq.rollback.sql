BEGIN;

select _v.unregister_patch( '001-fix-input-uniq' );

alter table input drop constraint input_input_key;

COMMIT;
