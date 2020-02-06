-- Remove report_probe_asn_idx and report_probe_cc_probe_asn_idx
-- Formatted with pgformatter 3.3

BEGIN;
SELECT
    _v.unregister_patch ('021-add-report-index');
DROP INDEX report_probe_asn_idx;
DROP INDEX report_probe_cc_probe_asn_idx;
COMMIT;
