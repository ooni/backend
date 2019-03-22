BEGIN;

select _v.register_patch( '013-ooexplr-meta', ARRAY[ '012-sha256-input-uniq' ], NULL );

CREATE TABLE ooexpl_bucket_msm_count (
    "count" bigint,
    "probe_asn" integer,
    "probe_cc" character(2),
    "bucket_date" date,
    CONSTRAINT ooexpl_bucket_msm_count_pkey PRIMARY KEY (probe_asn, probe_cc, bucket_date)
);

comment on table ooexpl_bucket_msm_count is 'OONI Explorer stats table for counting the total number of measurements since the beginning of time by probe_cc and probe_asn';

INSERT INTO ooexpl_bucket_msm_count ("count", "probe_asn", "probe_cc", "bucket_date")
SELECT
COUNT(msm_no) as "count",
probe_asn,
probe_cc,
bucket_date
FROM measurement
JOIN report ON report.report_no = measurement.report_no
JOIN autoclaved ON autoclaved.autoclaved_no = report.autoclaved_no
GROUP BY bucket_date, probe_asn, probe_cc;

CREATE TABLE ooexpl_recent_msm_count (
    "count" bigint,
    "probe_cc" character(2),
    "probe_asn" integer,
    "test_name" ootest,
    "test_day" timestamp without time zone,
    "bucket_date" date,
    CONSTRAINT ooexpl_recent_msm_count_pkey PRIMARY KEY (probe_asn, probe_cc, test_name, test_day, bucket_date)
);

INSERT INTO ooexpl_recent_msm_count ("count", "probe_cc", "probe_asn", "test_name", "test_day", "bucket_date")
SELECT
COUNT(msm_no) as "count",
probe_cc,
probe_asn,
test_name,
date_trunc('day', measurement_start_time) as test_day,
bucket_date
FROM measurement
JOIN report ON report.report_no = measurement.report_no
JOIN autoclaved ON autoclaved.autoclaved_no = report.autoclaved_no
WHERE measurement_start_time > current_date - interval '31 day'
GROUP BY probe_cc, probe_asn, test_name, test_start_time, bucket_date, test_day;

comment on table ooexpl_recent_msm_count is 'OONI Explorer stats table for counting measurements by probe_cc, probe_asn from the past 30 days';

CREATE MATERIALIZED VIEW ooexpl_website_msmts AS
    SELECT
    measurement.msm_no,
    input.input_no,
    probe_asn,
    probe_cc,
    CASE
        WHEN blocking != 'false' AND blocking != NULL THEN TRUE
        WHEN measurement.msm_no IN (SELECT msm_no FROM http_request_fp) THEN TRUE
        ELSE FALSE
    END as anomaly,
    CASE
        WHEN measurement.msm_no IN (SELECT msm_no FROM http_request_fp) THEN TRUE
        ELSE FALSE
    END as confirmed,
    CASE
        WHEN control_failure != NULL OR blocking = NULL THEN TRUE
        ELSE FALSE
    END as failure,
    blocking,
    http_experiment_failure,
    dns_experiment_failure,
    control_failure,
    bucket_date
    FROM measurement
    JOIN input ON input.input_no = measurement.input_no
    JOIN report ON report.report_no = measurement.report_no
    JOIN http_verdict ON http_verdict.msm_no = measurement.msm_no
    JOIN autoclaved ON autoclaved.autoclaved_no = report.autoclaved_no
    WHERE test_name = 'web_connectivity'
    AND measurement_start_time > current_date - interval '31 day';

CREATE INDEX "ooexpl_website_msmts_anomaly_idx" ON "public"."ooexpl_website_msmts"("anomaly");
CREATE INDEX "ooexpl_website_msmts_confirmed_idx" ON "public"."ooexpl_website_msmts"("confirmed");
CREATE INDEX "ooexpl_website_msmts_failure_idx" ON "public"."ooexpl_website_msmts"("failure");
CREATE INDEX "ooexpl_website_msmts_probe_cc_idx" ON "public"."ooexpl_website_msmts"("probe_cc");
CREATE INDEX "ooexpl_website_msmts_probe_asn_idx" ON "public"."ooexpl_website_msmts"("probe_asn");
CREATE INDEX "ooexpl_website_msmts_input_no_idx" ON "public"."ooexpl_website_msmts"("input_no");

COMMIT;
