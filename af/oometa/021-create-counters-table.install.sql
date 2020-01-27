-- Create counters table
-- See analysis/counters_table.adoc
-- Formatted with pgformatter 3.3

BEGIN;
SELECT
    _v.register_patch ('021-counters-table',
        ARRAY['020-new-test-names'],
        NULL);

CREATE TABLE counters (
    "measurement_start_day" DATE,
    "test_name" TEXT,
    "probe_cc" CHARACTER (2) NOT NULL,
    "probe_asn" INTEGER NOT NULL,
    "input" TEXT,
    "anomaly" BOOLEAN,
    "confirmed" BOOLEAN,
    "failure" BOOLEAN,
    "count" INTEGER NOT NULL
);

CREATE INDEX counters_brin_multi_idx ON counters
  USING BRIN (
    measurement_start_day,
    test_name,
    probe_cc,
    probe_asn,
    input,
    CAST(anomaly AS char),
    CAST(confirmed AS char),
    CAST(failure AS char)
  )
  WITH (pages_per_range = 32);


COMMIT;



