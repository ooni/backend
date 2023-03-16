(
    SELECT
        measurement.input_no,
        measurement.measurement_start_time,
        report.test_start_time,
        concat('temp-id', '-', measurement.msm_no) AS measurement_id,
        measurement.report_no,
        coalesce(measurement.anomaly, FALSE) AS anomaly,
        coalesce(measurement.confirmed, FALSE) AS confirmed,
        coalesce(measurement.msm_failure, FALSE) AS msm_failure,
        coalesce('{}') AS scores,
        measurement.exc AS exc,
        measurement.residual_no,
        report.report_id,
        report.probe_cc,
        report.probe_asn,
        report.test_name,
        report.report_no,
        coalesce(input.input, NULL) AS input
    FROM
        measurement
    LEFT OUTER JOIN input ON measurement.input_no = input.input_no
JOIN report ON report.report_no = measurement.report_no
WHERE
    report.probe_cc = 'IQ'
    AND measurement.measurement_start_time <= '2019-12-06T00:00:00'::timestamp
    AND coalesce(measurement.confirmed, FALSE) = TRUE
ORDER BY
    test_start_time DESC
LIMIT 50 OFFSET 0)
UNION (
    SELECT
        coalesce(0) AS m_input_no,
        fastpath.measurement_start_time AS test_start_time,
        fastpath.measurement_start_time,
        concat('temp-fid-', fastpath.tid) AS measurement_id,
        coalesce(0) AS m_report_no,
        coalesce(FALSE) AS anomaly,
        coalesce(FALSE) AS confirmed,
        coalesce(FALSE) AS msm_failure,
        CAST(fastpath.scores AS VARCHAR) AS anon_2,
        coalesce(ARRAY[0]) AS exc,
        coalesce(0) AS residual_no,
        fastpath.report_id,
        fastpath.probe_cc,
        fastpath.probe_asn,
        fastpath.test_name,
        coalesce(0) AS report_no,
        fastpath.input AS input
    FROM
        fastpath
    WHERE
        fastpath.measurement_start_time <= '2019-12-06T00:00:00'::timestamp
        AND fastpath.probe_cc = 'IQ'
    ORDER BY
        test_start_time DESC
    LIMIT 50 OFFSET 0);

