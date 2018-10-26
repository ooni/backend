BEGIN;

select _v.register_patch( '009-simhash',  ARRAY[ '008-measurements-index' ], NULL );

-- This table is empty, "inline" computation turned out to be as efficient as
-- more complex scheme with caching of body_sha256 values that tried to avoid
-- duplicate simhash computation. Moreover, inline storage is more efficient as
-- it has no row overhead.

DROP TABLE http_body_simhash;

ALTER TABLE http_control
    ADD COLUMN body_simhash bigint NULL,
    ADD COLUMN body_text_simhash bigint NULL
;

ALTER TABLE http_request
    ADD COLUMN body_simhash bigint NULL,
    ADD COLUMN body_text_simhash bigint NULL
;

COMMIT;
