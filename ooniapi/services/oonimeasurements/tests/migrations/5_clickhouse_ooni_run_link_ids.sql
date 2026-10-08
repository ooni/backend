-- The analysis_web_measurement and obs_web samples have no ooni_run_link_id
-- at all, while in production about half of the measurements come from an
-- OONI Run link. Give the samples the ten most common production link ids
-- (2026-10-08, one day of analysis_web_measurement), in about the same shares,
-- picked by measurement_uid so that both tables agree.

ALTER TABLE analysis_web_measurement UPDATE ooni_run_link_id = multiIf(
    cityHash64(measurement_uid) % 1000 < 487, '',
    cityHash64(measurement_uid) % 1000 < 934, '00104',
    cityHash64(measurement_uid) % 1000 < 954, '00105',
    cityHash64(measurement_uid) % 1000 < 972, '00108',
    cityHash64(measurement_uid) % 1000 < 983, '10006',
    cityHash64(measurement_uid) % 1000 < 988, '10005',
    cityHash64(measurement_uid) % 1000 < 993, '00106',
    cityHash64(measurement_uid) % 1000 < 997, '10375',
    cityHash64(measurement_uid) % 1000 < 999, '10236',
    '10004'
) WHERE 1 SETTINGS mutations_sync = 1;

ALTER TABLE obs_web UPDATE ooni_run_link_id = multiIf(
    cityHash64(measurement_uid) % 1000 < 487, '',
    cityHash64(measurement_uid) % 1000 < 934, '00104',
    cityHash64(measurement_uid) % 1000 < 954, '00105',
    cityHash64(measurement_uid) % 1000 < 972, '00108',
    cityHash64(measurement_uid) % 1000 < 983, '10006',
    cityHash64(measurement_uid) % 1000 < 988, '10005',
    cityHash64(measurement_uid) % 1000 < 993, '00106',
    cityHash64(measurement_uid) % 1000 < 997, '10375',
    cityHash64(measurement_uid) % 1000 < 999, '10236',
    '10004'
) WHERE 1 SETTINGS mutations_sync = 1
