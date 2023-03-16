BEGIN;

select _v.register_patch( '017-ooexpl_wc_input_counts', ARRAY[ '016-ooexpl_wc_confirmed' ], NULL );

/*
INSERT INTO ooexpl_wc_input_counts
(test_day, anomaly_count, confirmed_count, failure_count, total_count, input, bucket_date, probe_cc, probe_asn)
SELECT
date_trunc('day', test_start_time) as test_day,
COALESCE(sum(CASE WHEN anomaly = TRUE AND confirmed = FALSE AND msm_failure = FALSE THEN 1 ELSE 0 END), 0) AS anomaly_count,
COALESCE(sum(CASE WHEN confirmed = TRUE THEN 1 ELSE 0 END), 0) AS confirmed_count,
COALESCE(sum(CASE WHEN msm_failure = TRUE THEN 1 ELSE 0 END), 0) AS failure_count, COUNT(*) as total_count,
input,
bucket_date,
probe_cc,
probe_asn
FROM measurement
JOIN input ON input.input_no = measurement.input_no
JOIN report ON report.report_no = measurement.report_no
JOIN autoclaved ON report.autoclaved_no = autoclaved.autoclaved_no
WHERE test_start_time >= current_date - interval '31 day'
AND test_start_time < current_date
AND test_name = 'web_connectivity'
GROUP BY test_day, input, bucket_date, probe_cc, probe_asn;
*/

CREATE TABLE ooexpl_wc_input_counts (
    input TEXT,
    confirmed_count BIGINT NOT NULL,
    anomaly_count BIGINT NOT NULL,
    failure_count BIGINT NOT NULL,
    total_count BIGINT NOT NULL,
    test_day TIMESTAMP NOT NULL,
    bucket_date DATE,
    probe_cc CHARACTER(2) NOT NULL,
    probe_asn INTEGER NOT NULL,
    CONSTRAINT ooexpl_wc_input_unique_day_bucket_cc_asn_input UNIQUE (test_day, bucket_date, probe_cc, probe_asn, input)
);

CREATE INDEX "ooexpl_wc_input_counts_probe_cc_idx" ON "ooexpl_wc_input_counts"("probe_cc");
CREATE INDEX "ooexpl_wc_input_counts_probe_asn_idx" ON "ooexpl_wc_input_counts"("probe_asn");
CREATE INDEX "ooexpl_wc_input_counts_input_idx" ON "ooexpl_wc_input_counts"("input");

COMMIT;
