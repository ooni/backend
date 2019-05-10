BEGIN;

select _v.register_patch( '014-ooexpl-insert', ARRAY[ '013-ooexpl-tables' ], NULL );

INSERT INTO ooexpl_bucket_msm_count ("count", "probe_asn", "probe_cc", "bucket_date")
SELECT
COUNT(msm_no) as "count",
probe_asn,
probe_cc,
bucket_date
FROM measurement
JOIN report ON report.report_no = measurement.report_no
JOIN autoclaved ON autoclaved.autoclaved_no = report.autoclaved_no
GROUP BY 2,3,4;

INSERT INTO ooexpl_daily_msm_count ("count", "probe_cc", "probe_asn", "test_name", "test_day", "bucket_date")
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
WHERE measurement_start_time > current_date - interval '31 day' AND test_name IS NOT NULL
GROUP BY 2,3,4,5,6;

COMMIT;
