BEGIN;

select _v.unregister_patch( '002-features' );

drop table badmeta_tpl;
drop table badmeta;
drop extension pgcrypto;
drop table residual;
drop table http_body_simhash;
alter table http_request drop column body_sha256;
alter table http_control drop column body_sha256;
drop domain sha256;
alter table measurement_blob drop column input, drop column exc, drop column residual, add column input_no integer;
alter table measurement drop column exc, drop column residual_no;
comment on column tcp.control_failure is NULL;
alter table tcp drop column control_api_failure;
drop table dns_a_blob;
alter table dns_a drop column control_cname, drop column test_cname;

COMMIT;
