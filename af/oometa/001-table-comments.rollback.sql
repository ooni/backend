BEGIN;

select _v.unregister_patch( '001-table-comments' );

comment on table autoclaved is NULL;
comment on table software is NULL;
comment on table report is NULL;
comment on table badblob is NULL;
comment on table input is NULL;
comment on table measurement is NULL;
comment on table domain is NULL;
comment on table tcp is NULL;
comment on table dns_a is NULL;
comment on table http_control is NULL;
comment on table http_request is NULL;
comment on table http_verdict is NULL;

COMMIT;
