BEGIN;

select _v.unregister_patch( '003-msm-index' );

-- Bring our bugs back!
alter table http_control alter column msm_no drop not null;
alter table http_request alter column msm_no drop not null;
alter table http_verdict alter column msm_no drop not null;
alter table tcp alter column msm_no drop not null;

-- MOAR full-scans!
drop index dns_a_msm_no_idx;
drop index http_control_msm_no_idx;
drop index http_request_msm_no_idx;
drop index http_verdict_msm_no_idx;
drop index tcp_msm_no_idx;

COMMIT;
