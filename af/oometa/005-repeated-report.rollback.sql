BEGIN;

select _v.unregister_patch( '005-repeated-report' );

drop function ooconstraint_repeated_report();
drop table repeated_report;
drop domain sha512;
drop sequence dupgrp_no_seq;

COMMIT;
