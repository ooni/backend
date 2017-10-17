BEGIN;

select _v.register_patch( '006-vanilla-tor', ARRAY[ '005-repeated-report' ], NULL );

-- Everything goes to `public` schema.


CREATE TABLE vanilla_tor (
    msm_no                  int4 references measurement,
    success                 bool null,
    error                   bool null,
    timeout                 int4,
    tor_progress            int4,
    tor_progress_tag        text,
    tor_progress_summary    text,
    tor_version             text,
    tor_log                 text,
    transport_name          text
);

COMMIT;
