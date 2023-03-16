BEGIN;

select _v.register_patch( '006-repeated-report',  ARRAY[ '005-repeated-report' ], NULL );

comment on table repeated_report is 'Duplicate report files from private/canned';

COMMIT;
