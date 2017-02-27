BEGIN;

select _v.register_patch( '000-init', NULL, NULL );

-- Everything goes to `public` schema.

create domain sha1 as bytea check (octet_length(value) = 20);

create domain size4 as int4 check (value >= 0);

-- Metadata of `canned` is not recorded as it's useful only for some
-- statistics that can be computed without postgres and, moreover,
-- `canned` is not `public` data.

create table autoclaved (
    autoclaved_no   serial  primary key,
    filename        text    unique not null,
    bucket_date     date    not null,
    code_ver        int4    not null,
    file_size       size4   not null,
    file_crc32      int4    not null,
    file_sha1       sha1    not null,
    CHECK(substring(filename from 1 for 11) = (bucket_date || '/'))
);

comment on column autoclaved.filename is 'Name of compressed blob relative to …/autoclaved like `2017-01-01/facebook_messenger.0.tar.lz4`';
comment on column autoclaved.code_ver is 'Version of code processed this autoclaved file (used for partial updates)';

create type ootest as enum (
    'web_connectivity',
    'http_requests',
    'dns_consistency',
    'http_invalid_request_line',
    'bridge_reachability',
    'tcp_connect',
    'http_header_field_manipulation',
    'http_host',
    'multi_protocol_traceroute',
    'meek_fronted_requests_test',
    'whatsapp',
    'vanilla_tor',
    'facebook_messenger',
    'ndt'
);

create table software (
    software_no         serial  primary key,
    test_name           text    not null,
    test_version        text    not null,
    software_name       text    not null,
    software_version    text    not null,
    UNIQUE (test_name, test_version, software_name, software_version)
);

-- Some report fields are ignored while filling `report` table.  Some of them
-- are not filled in modern reports (or have same value): probe_city,
-- backend_version, data_format_version. Other have questionable value for
-- indexing and aggregation (may be added later): input_hashes (list of
-- hashes), options (CLI), test_helpers. `test_keys` are expanded to features
-- in different tables.

create table report (
    report_no       serial  primary key,
    autoclaved_no   int4    references autoclaved,
    test_start_time timestamp without time zone not null,
    probe_cc        char(2) not null,       -- 'ZZ' is replacement for NULL
    probe_asn       int4    not null,       -- 0 is replacement for NULL, was string 'ASxxxx' before
    probe_ip        inet    null,           -- "127.0.0.1" becomes NULL
    test_name       ootest  null,           -- NULL for tests without known parsed metadata
    badtail         size4   null,
    textname        text    unique not null,-- AKA `report_filename`
    orig_sha1       sha1    not null,
    report_id       text    unique not null,-- "20170129T000004Z_AS0_JjsPsc…AJZA" OR base32(orig_sha1)
    software_no     int4    references software
    -- CHECK(substring(textname from 1 for 11) = (bucket_date || '/'))
);

comment on column report.textname is 'Name of original reports-raw file like `2017-01-01/20170101T000056Z-ZZ-AS0-facebook_messenger-20170101T000013Z_AS0_a6dK…JVMO-0.1.0-probe.yaml`';

create sequence msmblob_msm_no_seq;

-- badblob `src_off` and `src_size` -- offsets within reports-raw file from
-- canned blob are not recorded here as canned files are not recorded here.
-- The reason to record badblob is preservation of `msm_no` on re-generation
-- of measurements.

create table badblob (
    msm_no      integer not null default nextval('msmblob_msm_no_seq') primary key,
    report_no   int4    references report,
    orig_sha1   sha1    not null
);

-- `frame_off` and `frame_size` do not deserve separate relation as
-- de-duplication will save almost nothing: 8 bytes per measurement become
-- 4 bytes per measurement + 12 bytes per frame (without indexes). That reduces
-- 770 kb of metadata down to 600 kb of frame-related(!) metadata for 2017-01-01

create table measurement (
    msm_no                  integer not null default nextval('msmblob_msm_no_seq') primary key,
    report_no               int4    references report,
    frame_off               size4   not null,
    frame_size              size4   not null,
    intra_off               size4   not null,
    intra_size              size4   not null,
    measurement_start_time  timestamp without time zone null,
    test_runtime            real    null,
    orig_sha1               sha1    not null,
    id                      uuid    not null,
    input                   text    null
);

comment on column measurement.frame_off is 'Offset within autoclaved.filename';

COMMIT;
