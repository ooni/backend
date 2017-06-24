BEGIN;

select _v.register_patch( '000-originas', NULL, NULL );

-- Everything goes to `public` schema.

create table originas (
    origin  cidr    not null,
    asn     int4    not null
);

create index on originas using gist (origin inet_ops);

comment on table originas is 'source is http://archive.routeviews.org/dnszones/originas.bz2';

COMMIT;
