-- Create fastpath tables
-- Formatted with pgformatter 3.3

BEGIN;

SELECT
    _v.register_patch ('017-fastpath',
        ARRAY['016-ooexpl_wc_confirmed'],
        NULL);

CREATE TABLE fastpath (
    "tid" TEXT PRIMARY KEY,
    "report_id" text NOT NULL,
    "input" TEXT,
    "probe_cc" character (2) NOT NULL,
    "probe_asn" integer NOT NULL,
    "test_name" ootest,
    "test_start_time" timestamp without time zone NOT NULL,
    "measurement_start_time" timestamp without time zone,
    "platform" text,
    "filename" text, -- will be NULL after files are deleted
    "scores" JSON NOT NULL
);

CREATE INDEX report_id_idx ON fastpath(report_id);

CREATE INDEX input_idx ON fastpath(input);

COMMENT ON TABLE fastpath IS 'Measurements created by fastpath';

COMMENT ON COLUMN fastpath.tid IS 'Trivial ID';

COMMENT ON COLUMN fastpath.filename IS 'File served by the fastpath host containing the raw measurement';

COMMENT ON COLUMN fastpath.scores IS 'Scoring metadata';

COMMIT;
