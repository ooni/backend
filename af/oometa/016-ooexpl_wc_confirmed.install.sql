BEGIN;

select _v.register_patch( '016-ooexpl_wc_confirmed', ARRAY[ '015-fingerprint-fix' ], NULL );

CREATE MATERIALIZED VIEW ooexpl_wc_confirmed AS
SELECT
COALESCE(SUM(CASE WHEN confirmed = TRUE THEN 1 ELSE 0 END), 0) as confirmed_count,
COUNT(*) as msm_count,
date_trunc('day', test_start_time) as test_day,
probe_cc,
probe_asn
FROM (
	SELECT
	DISTINCT input as input,
	test_start_time,
	probe_cc,
	probe_asn,
	bool_or(confirmed) as confirmed
	FROM measurement
	JOIN input ON input.input_no = measurement.input_no
	JOIN report ON report.report_no = measurement.report_no
	WHERE test_start_time >= current_date - interval '2 months'
	AND test_start_time < current_date - interval '1 day'
	AND test_name = 'web_connectivity'
	GROUP BY 1,2,3,4
) as wc
GROUP BY 3,4,5;

COMMIT;
