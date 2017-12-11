BEGIN;

select _v.register_patch( '006-reingestion',  ARRAY[ '005-repeated-report' ], NULL );

ALTER SEQUENCE autoclaved_autoclaved_no_seq RENAME TO autoclaved_no_seq;

DROP TABLE report_meta;
DROP TABLE report_blob;
DROP TABLE measurement_meta;
DROP TABLE measurement_blob;
DROP TABLE measurement_exc;
DROP TABLE badmeta_tpl;
DROP TABLE dns_a_tpl;

-- `badblob` is a nice table, but we can't properly ingest it right now and
-- it's something that does not actually exist after `autoclaved` stage, these
-- bad blobs are lost during autoclaving, only canning preserves them.
DROP TABLE badblob;

ALTER TABLE badmeta DROP COLUMN textname;

-- re-ingest `vanilla_tor`
UPDATE autoclaved SET code_ver = 4
WHERE code_ver = 3 AND NOT EXISTS (
    SELECT 1 FROM report
    WHERE autoclaved_no = autoclaved.autoclaved_no
      AND test_name = 'vanilla_tor'
);

COMMIT;
