-- /api/v1/aggregation counts measurements by outcome over windows of up to
-- years, reading every measurement in the window. This projection keeps those
-- counts per day, probe_cc, probe_asn and test_name, ~134 measurements per
-- row in production, and answers the full days of any aggregation filtering
-- and grouping only by those (see aggregation.py). Its count expressions must
-- stay identical to the endpoint's, or ClickHouse will not use it.
--
-- ReplacingMergeTree needs deduplicate_merge_projection_mode to allow
-- projections; "rebuild" recomputes them for merged parts, so they always
-- match the deduplicated rows. Requires ClickHouse 24.8 or later.
--
-- Production (ooni/devops schema.sql). MATERIALIZE PROJECTION is a mutation
-- reading these columns of every part, so run it off-peak:
--   ALTER TABLE ooni.fastpath ON CLUSTER oonidata_cluster MODIFY SETTING deduplicate_merge_projection_mode = 'rebuild';
--   ALTER TABLE ooni.fastpath ON CLUSTER oonidata_cluster ADD PROJECTION IF NOT EXISTS agg_day_cc_asn_test (
--       SELECT toDate(measurement_start_time), probe_cc, probe_asn, test_name,
--           countIf(anomaly = 't' AND confirmed = 'f' AND msm_failure = 'f'),
--           countIf(confirmed = 't' AND msm_failure = 'f'),
--           countIf(msm_failure = 't'),
--           countIf(anomaly = 'f' AND confirmed = 'f' AND msm_failure = 'f'),
--           count()
--       GROUP BY toDate(measurement_start_time), probe_cc, probe_asn, test_name);
--   ALTER TABLE ooni.fastpath ON CLUSTER oonidata_cluster MATERIALIZE PROJECTION agg_day_cc_asn_test;

ALTER TABLE default.fastpath MODIFY SETTING deduplicate_merge_projection_mode = 'rebuild';

ALTER TABLE default.fastpath ADD PROJECTION IF NOT EXISTS agg_day_cc_asn_test (
    SELECT toDate(measurement_start_time), probe_cc, probe_asn, test_name,
        countIf(anomaly = 't' AND confirmed = 'f' AND msm_failure = 'f'),
        countIf(confirmed = 't' AND msm_failure = 'f'),
        countIf(msm_failure = 't'),
        countIf(anomaly = 'f' AND confirmed = 'f' AND msm_failure = 'f'),
        count()
    GROUP BY toDate(measurement_start_time), probe_cc, probe_asn, test_name
);

ALTER TABLE default.fastpath MATERIALIZE PROJECTION agg_day_cc_asn_test SETTINGS mutations_sync = 1
