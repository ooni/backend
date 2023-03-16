BEGIN;

select _v.unregister_patch( '017-ooexpl_wc_input_counts');

DROP TABLE ooexpl_wc_input_counts;

DROP INDEX "ooexpl_wc_input_counts_probe_cc_idx";
DROP INDEX "ooexpl_wc_input_counts_probe_asn_idx";
DROP INDEX "ooexpl_wc_input_counts_input_idx";

COMMIT;
