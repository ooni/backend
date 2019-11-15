-- Create fastpath tables
-- Formatted with pgformatter 3.3

BEGIN;

SELECT
    _v.register_patch ('018-fastpath', ARRAY['017-ooexpl_wc_input_counts'], NULL);

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

CREATE INDEX report_id_idx ON fastpath (report_id);

CREATE INDEX input_idx ON fastpath (input);

CREATE INDEX measurement_start_time_idx ON fastpath (measurement_start_time);

COMMENT ON TABLE fastpath IS 'Measurements created by fastpath';

COMMENT ON COLUMN fastpath.tid IS 'Trivial ID';

COMMENT ON COLUMN fastpath.filename IS 'File served by the fastpath host containing the raw measurement';

COMMENT ON COLUMN fastpath.scores IS 'Scoring metadata';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'amsapi') THEN
        GRANT SELECT ON fastpath TO amsapi;
    END IF;
END
$$;

GRANT SELECT ON tasks TO reader;

GRANT SELECT ON fastpath TO readonly;

COMMIT;
