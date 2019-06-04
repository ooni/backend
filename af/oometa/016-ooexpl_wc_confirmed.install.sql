BEGIN;

select _v.register_patch( '016-ooexpl_wc_confirmed', ARRAY[ '015-fingerprint-fix' ], NULL );

/* Store precomputed `confirmed` count and `msm_count`
from the web_connectivity table. Used by OONI Explorer. */

/*
INSERT INTO ooexpl_wc_confirmed
SELECT
COALESCE(SUM(CASE WHEN confirmed = TRUE THEN 1 ELSE 0 END), 0) as confirmed_count,
COUNT(*) as msm_count,
test_day,
bucket_date,
probe_cc,
probe_asn
FROM (
	SELECT
	DISTINCT input as input,
  date_trunc('day', test_start_time) as test_day,
	probe_cc,
	probe_asn,
  bucket_date,
	bool_or(confirmed) as confirmed
	FROM measurement
	JOIN input ON input.input_no = measurement.input_no
	JOIN report ON report.report_no = measurement.report_no
  JOIN autoclaved ON autoclaved.autoclaved_no = report.autoclaved_no
	WHERE test_start_time < current_date - interval '1 day'
	AND test_start_time > current_date - interval '31 day'
	AND test_name = 'web_connectivity'
	GROUP BY input, test_start_time, probe_cc, probe_asn, bucket_date
) as wc
GROUP BY test_day, probe_cc, probe_asn, bucket_date;
*/

CREATE TABLE ooexpl_wc_confirmed (
    confirmed_count BIGINT NOT NULL,
    msm_count BIGINT NOT NULL,
    test_day TIMESTAMP NOT NULL,
    bucket_date DATE,
    probe_cc CHARACTER(2) NOT NULL,
    probe_asn INTEGER NOT NULL,
    CONSTRAINT unique_day_bucket_cc_asn UNIQUE (test_day, bucket_date, probe_cc, probe_asn)
  ) ;


COMMIT;
