BEGIN;

select _v.register_patch( '010-badblob',  ARRAY[ '009-simhash' ], NULL );

-- Original reason for `badblob` table was to preserve a `msm_no` for possible
-- re-generation of measurements later. It's not longer relevant as OOID is
-- going to be stamped on historical measurements:
-- https://github.com/TheTorProject/ooni-pipeline/blob/master/docs/ooid-hash-prob.ipynb
create table badblob (
    -- Imagine a report that has no measurements! E.g. a half-empty broken
    -- badblob as a report. Alike report will unlikely have a report_no.
    -- So `filename` and `textname` are stored as canned files have no STRICT
    -- mapping to `autoclaved_no` and `report_no`, although names of compressed
    -- and uncompressed files usually match 1:1. Also, cardinality of the table
    -- is going to be low, so storage optimisations do not matter.
    filename        text    not null,
    textname        text    not null,
    canned_off      size4   not null,
    canned_size     size4   not null,
    bucket_date     date    not null,
    orig_sha1       sha1    not null,
    exc_str         text    not null,
    PRIMARY KEY (filename, textname, canned_off)
);

create index badblob_bucket_date_idx on badblob (bucket_date);

comment on table badblob is 'Debug: accounting exceptions during (canned -> autoclaved) process';

COMMIT;
