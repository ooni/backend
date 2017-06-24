BEGIN;

select _v.register_patch( '001-table-comments', ARRAY[ '000-init' ], NULL );

-- Everything goes to `public` schema.

-- Comments on tables visually separate "persistent" table in `\dt+` output
-- from "temporary" tables created while doing exploratory data analysis.

comment on table autoclaved is 'Metadata table for public/autoclaved files';
comment on table software is 'External dictionary of known ooniprobe tests implementations and versions to shrink `report` table';
comment on table report is 'Metadata for reports loosely corresponding to private/reports-raw files';
comment on table badblob is 'Metadata of malformed measurements blobs including truncated reports';
comment on table input is 'External dictionary of known test inputs to shrink `measurement` table';
comment on table measurement is 'Metadata for measurements stored within reports';
comment on table domain is 'External dictionary of known DNS domains to shrink `dns_a` table';
comment on table tcp is 'Features: state of TCP connect() for specific IP and port';
comment on table dns_a is 'Features: DNS resolution of `A` query';
comment on table http_control is 'Features: HTTP response got through "control" vantage point';
comment on table http_request is 'Features: HTTP response got through "test" vantage point';
comment on table http_verdict is 'Features: decision of ooniprobe regarding HTTP response';

COMMIT;
