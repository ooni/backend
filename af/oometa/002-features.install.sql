BEGIN;

select _v.register_patch( '002-features', ARRAY[ '001-fix-input-uniq' ], NULL );

-- Everything goes to `public` schema.

-- NB: postgresql can't place new columns into arbitrary place.
alter table dns_a
    alter column msm_no set not null,
    alter column domain_no set not null,
    add column control_cname int4[],
    add column test_cname int4[],
    add column ttl int4,
    add column resolver_hostname inet,
    add column client_resolver inet,
    add column control_failure text,
    add column test_failure text
;
comment on column dns_a.control_cname is 'Reference to `domain` table. Lack of CNAME is NULL, not zero-length array';
comment on column dns_a.test_cname is 'Reference to `domain` table. Lack of CNAME is NULL, not zero-length array';
comment on column dns_a.ttl is 'The first TTL of all DNS Resource Records';
comment on column dns_a.resolver_hostname is 'Internal resolver IP according to ~ /etc/resolv.conf';
comment on column dns_a.client_resolver is 'External resolver IP according to ~ whoami.akamai.net';

create table dns_a_tpl (
    msm_no              int4 not null,
    domain              text not null,
    control_ip          inet[],
    test_ip             inet[],
    control_cname       text[],
    test_cname          text[],
    ttl                 int4,
    resolver_hostname   inet,
    client_resolver     inet,
    control_failure     text,
    test_failure        text
);
comment on table dns_a_tpl is 'For `CREATE TABLE LIKE …` while loading';

alter table tcp add column control_api_failure text;
comment on column tcp.control_failure is 'per-address "failure" field for the experiment';
comment on column tcp.control_api_failure is '"control_failure" field of the measurement';

alter table measurement
    add column exc int4[], -- NULL == no errors, empty array takes space :)
    add column residual_no int4 not null; -- most of residual schemas should be quite common

alter table measurement_blob
    drop column input_no,
    add column input text, -- `input->input_no` mapping is too large to fit in RAM, so it's done at PG side
    add column exc int4[], -- 32bit MurMurhash3 of traces (to fix the most popluar ones first)
    add column residual jsonb not null;

create domain sha256 as bytea check (octet_length(value) = 32);

alter table http_control add column body_sha256 sha256;

alter table http_request add column body_sha256 sha256;

create table http_body_simhash (
    body_sha256         sha256  primary key,
    simhash_shi4mm3hi   int8    not null,
    simhash_shi4mm3lo   int8    not null
);
comment on table http_body_simhash is 'Features: simhash values for HTTP bodies';
comment on column http_body_simhash.simhash_shi4mm3hi is 'body | 4_word_shingles | MurMur3_128_high | simhash64';
comment on column http_body_simhash.simhash_shi4mm3lo is 'body | 4_word_shingles | MurMur3_128_low | simhash64';

create extension pgcrypto;
create table residual (
    residual_no serial  primary key,
    residual    jsonb   not null
);
-- I have not managed to write it as CONSTRAINT, so it's UNIQUE INDEX.
-- sha256 is used because of long residual values:
-- ERROR:  index row size 3008 exceeds maximum 2712 for index "residual_residual_key"
-- HINT:  Values larger than 1/3 of a buffer page cannot be indexed.
-- Consider a function index of an MD5 hash of the value, or use full text indexing.
create unique index residual_residual_sha256_key on residual (digest(residual::text, 'sha256'));
comment on table residual is 'Debug: pseudo-schema of json leftovers remaining after centrifugation';

create table badmeta (
    autoclaved_no   int4    not null,
    report_no       int4,   -- MAYBE references `report`
    textname        text,   -- used to lookup `report_filename` if report_no is NULL
    exc_report      int4[]  not null,
    exc_measurement int4[]  not null,
    CHECK(report_no IS NOT NULL OR textname IS NOT NULL)
);
comment on table badmeta is 'Debug: accounting exceptions while handling metadata during centrifugation';

create table badmeta_tpl (
    autoclaved_no   int4    not null,
    report_no       int4    not null,
    textname        text    not null,
    exc_report      int4    null,
    exc_measurement int4    null
    CHECK(exc_report IS NOT NULL OR exc_measurement IS NOT NULL)
);
comment on table badmeta_tpl is 'For `CREATE TABLE LIKE …` while loading';

COMMIT;
