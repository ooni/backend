BEGIN;

select _v.register_patch( '006-vanilla-tor', ARRAY[ '005-repeated-report' ], NULL );

-- Everything goes to `public` schema.

CREATE TABLE vanilla_tor (
    msm_no                  int4 not null, -- references measurement,
    timeout                 int4 not null,
    error                   text,
    tor_progress            int2 not null,
    success                 bool not null,
    tor_progress_tag        text,
    tor_progress_summary    text,
    tor_version             text not null,
    tor_log                 jsonb
);

COMMENT ON TABLE vanilla_tor IS 'Features: data from `vanilla_tor` measurements';

COMMIT;
