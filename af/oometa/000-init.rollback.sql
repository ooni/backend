BEGIN;

select _v.unregister_patch( '000-init' );

drop table measurement;
drop table badblob;
drop sequence msmblob_msm_no_seq;
drop table report;
drop table software;
drop type ootest;
drop table autoclaved;
drop domain size4;
drop domain sha1;

COMMIT;
