BEGIN;

SELECT _v.register_patch( '011-cleanup',  ARRAY[ '010-badblob' ], NULL );

COMMENT ON TABLE badrow IS 'Debug: accounting exceptions while feeding DB with COPY FROM STDIN';

-- `label` is a nice table, but we don't fill it right now and it creates
-- useless complexity without any extra value.  Moreover, the hack with manual
-- labeling is no longer useful at all as OONI Pipeline can do partial
-- re-ingestions as the indicators-of-censorship are updated in the pipeline code.
DROP TABLE label;

ALTER TABLE report ALTER COLUMN autoclaved_no SET NOT NULL;
ALTER TABLE measurement ALTER COLUMN report_no SET NOT NULL;

COMMIT;
