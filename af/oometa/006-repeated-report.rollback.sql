BEGIN;

select _v.unregister_patch( '006-repeated-report' );

comment on table repeated_report is null;

COMMIT;
