-- Searches by input read the input column of every measurement in their
-- window: fastpath is ordered by time, and input comes after it in the sort
-- key. A bloom filter per granule skips the granules an input is not in, so
-- a search for an input that was never measured (the bulk of production's
-- searches by input, see bench/test_bench_queries.py) reads almost nothing,
-- and one for a rare input reads only the granules holding it. It cannot
-- change results: a granule is only skipped when it cannot match.
--
-- Production has ~6K distinct inputs per granule, so at 1% false positives
-- the index takes ~7 KB per granule, ~3 GB for 3.7B measurements.
--
-- Production (ooni/devops schema.sql). MATERIALIZE INDEX is a mutation
-- reading input from every part, so run it off-peak:
--   ALTER TABLE ooni.fastpath ON CLUSTER oonidata_cluster ADD INDEX IF NOT EXISTS input_bloom_idx input TYPE bloom_filter(0.01) GRANULARITY 1;
--   ALTER TABLE ooni.fastpath ON CLUSTER oonidata_cluster MATERIALIZE INDEX input_bloom_idx;

ALTER TABLE default.fastpath ADD INDEX IF NOT EXISTS input_bloom_idx input TYPE bloom_filter(0.01) GRANULARITY 1;

ALTER TABLE default.fastpath MATERIALIZE INDEX input_bloom_idx SETTINGS mutations_sync = 1
