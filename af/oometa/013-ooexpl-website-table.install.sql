BEGIN;

select _v.register_patch( '013-ooexpl-website-table', ARRAY[ '012-sha256-input-uniq' ], NULL );

CREATE TABLE ooexpl_website_msm (
    msm_no integer PRIMARY KEY,
    input_no integer NOT NULL,
    probe_asn integer NOT NULL,
    probe_cc character(2) NOT NULL,
    measurement_start_time timestamp without time zone NOT NULL,
    anomaly boolean,
    confirmed boolean,
    failure boolean,
    bucket_date date
);

COMMIT;
