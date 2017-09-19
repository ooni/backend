BEGIN;

SELECT _v.register_patch( '005-anomaly-flags', ARRAY[ '004-measurements-index' ], NULL );

-- Everything goes to `public` schema.

ALTER TABLE measurement
    ADD COLUMN msm_failure boolean NULL,
    ADD COLUMN anomaly boolean NULL,
    ADD COLUMN confirmed boolean NULL
;

CREATE TABLE label (
    msm_no integer NOT NULL,
    msm_failure boolean NULL,
    anomaly boolean NULL,
    confirmed boolean NULL
);

COMMENT ON TABLE label IS 'Manual markup overriding corresponding flags in measurement table';

-- API declares following flags:
--
-- failure = COALESCE(label.msm_failure, measurement.msm_failure, false) OR measurement.exc IS NOT NULL OR measurement.residual_no IS NOT NULL
-- anomaly = COALESCE(label.anomaly, measurement.anomaly, false)
-- confirmed = COALESCE(label.confirmed, measurement.confirmed, false)

-- Following updates are not part of pipeline, these are just sample data.
UPDATE measurement SET anomaly = TRUE, confirmed = TRUE WHERE msm_no IN (SELECT msm_no FROM http_request_fp);
UPDATE measurement SET anomaly = TRUE WHERE msm_no IN (SELECT msm_no FROM http_verdict WHERE NOT body_length_match OR NOT headers_match OR NOT status_code_match);

COMMIT;
