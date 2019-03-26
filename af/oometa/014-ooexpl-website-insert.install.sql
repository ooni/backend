BEGIN;

select _v.register_patch( '014-ooexpl-website-insert', ARRAY[ '013-ooexpl-website-table' ], NULL );

INSERT INTO ooexpl_website_msm ("msm_no", "input_no", "probe_asn", "probe_cc", "measurement_start_time", "anomaly", "confirmed", "failure", "bucket_date")
SELECT
    measurement.msm_no,
    input.input_no,
    probe_asn,
    probe_cc,
    measurement_start_time,
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
    bucket_date
    FROM measurement
    JOIN input ON input.input_no = measurement.input_no
    JOIN report ON report.report_no = measurement.report_no
    JOIN http_verdict ON http_verdict.msm_no = measurement.msm_no
    JOIN autoclaved ON autoclaved.autoclaved_no = report.autoclaved_no
    WHERE test_name = 'web_connectivity'
    AND measurement_start_time > current_date - interval '31 day'
ON CONFLICT (msm_no) DO UPDATE SET
    anomaly = EXCLUDED.anomaly,
    confirmed = EXCLUDED.confirmed,
    failure = EXCLUDED.failure;

COMMIT;
