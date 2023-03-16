-- Add index to report table ooni/backend#327
BEGIN;
SELECT
    _v.register_patch ('021-add-report-index',
        ARRAY['020-new-test-names'],
        NULL);
CREATE INDEX report_probe_asn_idx ON report (probe_asn);
CREATE INDEX report_probe_cc_probe_asn_idx ON report (probe_cc, probe_asn);
COMMIT;
