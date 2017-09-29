BEGIN;

select _v.unregister_patch( '000-init' );

drop table http_verdict;
drop table http_request;
drop table http_control;
drop table dns_a;
drop table tcp;
drop table domain;
drop table measurement_blob;
drop table measurement_meta;
drop table measurement;
drop table input;
drop table badblob;
drop sequence msm_no_seq;
drop table report_blob;
drop table report_meta;
drop table report;
drop sequence report_no_seq;
drop table software;
drop type ootest;
drop table autoclaved;
drop domain size4;
drop domain sha1;

COMMIT;
