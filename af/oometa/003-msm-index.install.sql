BEGIN;

select _v.register_patch( '003-msm-index', ARRAY[ '002-features' ], NULL );

-- Everything goes to `public` schema.

-- These indexes are done to ease DELETE of measurements features on partial
-- table update. It's questionable of partial update is good idea or not
-- (maybe, writing to separate table is actually better), but that's current
-- decision that seems to be good enough.  It's not unique and it's not primary
-- key as most of measurements may have several corresponding feature rows.
create index dns_a_msm_no_idx on dns_a (msm_no);
create index http_control_msm_no_idx on http_control (msm_no);
create index http_request_msm_no_idx on http_request (msm_no);
create index http_verdict_msm_no_idx on http_verdict (msm_no);
create index tcp_msm_no_idx on tcp (msm_no);

-- Fix ancient bugs :)
alter table http_control alter column msm_no set not null;
alter table http_request alter column msm_no set not null;
alter table http_verdict alter column msm_no set not null;
alter table tcp alter column msm_no set not null;

COMMIT;
