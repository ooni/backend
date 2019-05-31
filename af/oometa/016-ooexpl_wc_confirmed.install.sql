BEGIN;

select _v.register_patch( '016-ooexpl_wc_confirmed', ARRAY[ '015-fingerprint-fix' ], NULL );

/* Store precomputed `confirmed` count and `msm_count`
from the web_connectivity table. Used by OONI Explorer. */

CREATE TABLE ooexpl_wc_confirmed (
    confirmed_count BIGINT NOT NULL,
    msm_count BIGINT NOT NULL,
    test_day TIMESTAMP NOT NULL,
    probe_cc CHARACTER(2) NOT NULL,
    probe_asn INTEGER NOT NULL,
    CONSTRAINT unique_day_cc_asn UNIQUE (test_day, probe_cc, probe_asn)
  ) ;

COMMIT;
