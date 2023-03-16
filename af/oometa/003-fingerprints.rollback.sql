BEGIN;

select _v.unregister_patch( '003-fingerprints' );

drop table fingerprint;
drop table measurement_exc;
drop table http_request_fp;

COMMIT;
