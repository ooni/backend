BEGIN;

select _v.register_patch( '013-ooexpl-tables', ARRAY[ '012-sha256-input-uniq' ], NULL );

CREATE TABLE ooexpl_bucket_msm_count (
    "count" integer,
    "probe_asn" integer,
    "probe_cc" character(2),
    "bucket_date" date,
    CONSTRAINT ooexpl_bucket_msm_count_pkey PRIMARY KEY (probe_asn, probe_cc, bucket_date)
);

comment on table ooexpl_bucket_msm_count is 'OONI Explorer stats table for counting the total number of measurements since the beginning of time by probe_cc and probe_asn';

CREATE TABLE ooexpl_daily_msm_count (
    "count" integer,
    "probe_cc" character(2),
    "probe_asn" integer,
    "test_name" ootest,
    "test_day" date,
    "bucket_date" date,
    CONSTRAINT ooexpl_daily_msm_count_pkey PRIMARY KEY (probe_asn, probe_cc, test_name, test_day, bucket_date)
);

comment on table ooexpl_daily_msm_count is 'OONI Explorer stats table for counting measurements by probe_cc, probe_asn from the past 30 days';

COMMIT;
