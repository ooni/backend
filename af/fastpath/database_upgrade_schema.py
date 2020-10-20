#!/usr/bin/env python3
"""
Roll-forward / rollback database schemas

Can be used from CLI and as a Python module
"""

from argparse import ArgumentParser

# Refresh / compare using
# ssh ams-pg.ooni.org -t pg_dump metadb -U shovel --schema-only | \
# grep -v  '^-' | uniq |  sed 's/\r$//' > database_upgrade_schema.sql
#
# meld database_upgrade_schema.py database_upgrade_schema.sql


def db_setup():
    """Setup fastpath database from scratch"""
    sql = """
SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

CREATE TYPE public.ootest AS ENUM (
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
    'ndt',
    'dash',
    'telegram',
    'psiphon',
    'tor'
);

ALTER TYPE public.ootest OWNER TO shovel;

SET default_tablespace = '';

SET default_with_oids = false;

CREATE TABLE public.autoclavedlookup (
    frame_off integer,
    frame_size integer,
    intra_off integer,
    intra_size integer,
    textname text,
    filename text,
    report_id text,
    input text
);

ALTER TABLE public.autoclavedlookup OWNER TO shovel;

CREATE TABLE public.citizenlab (
    domain text NOT NULL,
    url text NOT NULL,
    cc character(2),
    category_code text,
    priority smallint DEFAULT 256
);

ALTER TABLE public.citizenlab OWNER TO shovel;

COMMENT ON COLUMN public.citizenlab.domain IS 'FQDN or ipaddr without http and port number';

COMMENT ON COLUMN public.citizenlab.category_code IS 'Category from Citizen Lab';

CREATE UNLOGGED TABLE public.counters (
    measurement_start_day date,
    test_name text,
    probe_cc character(2) NOT NULL,
    probe_asn integer NOT NULL,
    input text,
    anomaly_count integer,
    confirmed_count integer,
    failure_count integer,
    measurement_count integer
);

ALTER TABLE public.counters OWNER TO shovel;

CREATE UNLOGGED TABLE public.counters_asn_noinput (
    measurement_start_day date,
    test_name text,
    probe_cc character(2),
    probe_asn integer,
    anomaly_count bigint,
    confirmed_count bigint,
    failure_count bigint,
    measurement_count bigint
);

ALTER TABLE public.counters_asn_noinput OWNER TO shovel;

CREATE UNLOGGED TABLE public.counters_noinput (
    measurement_start_day date,
    test_name text,
    probe_cc character(2),
    anomaly_count bigint,
    confirmed_count bigint,
    failure_count bigint,
    measurement_count bigint
);

ALTER TABLE public.counters_noinput OWNER TO shovel;

CREATE MATERIALIZED VIEW public.country_stats AS
 SELECT min(counters.measurement_start_day) AS first_bucket_date,
    count(DISTINCT counters.probe_asn) AS network_count,
    sum(counters.measurement_count) AS measurement_count,
    counters.probe_cc
   FROM public.counters
  GROUP BY counters.probe_cc
  WITH NO DATA;

ALTER TABLE public.country_stats OWNER TO shovel;

CREATE TABLE public.domain_input (
    domain text NOT NULL,
    input text NOT NULL,
    input_no integer
);

ALTER TABLE public.domain_input OWNER TO shovel;

CREATE TABLE public.fastpath (
    measurement_uid text NOT NULL,
    report_id text NOT NULL,
    input text,
    probe_cc character(2) NOT NULL,
    probe_asn integer NOT NULL,
    test_name public.ootest,
    test_start_time timestamp without time zone NOT NULL,
    measurement_start_time timestamp without time zone,
    filename text,
    scores json NOT NULL,
    platform text,
    anomaly boolean,
    confirmed boolean,
    msm_failure boolean,
    domain text,
    software_name text,
    software_version text
);

ALTER TABLE public.fastpath OWNER TO shovel;

COMMENT ON TABLE public.fastpath IS 'Measurements created by fastpath';

COMMENT ON COLUMN public.fastpath.measurement_uid IS 'Trivial ID';

COMMENT ON COLUMN public.fastpath.filename IS 'File served by the fastpath host containing the raw measurement';

COMMENT ON COLUMN public.fastpath.scores IS 'Scoring metadata';

CREATE MATERIALIZED VIEW public.global_by_month AS
 SELECT count(DISTINCT counters.probe_asn) AS networks_by_month,
    count(DISTINCT counters.probe_cc) AS countries_by_month,
    sum(counters.measurement_count) AS measurements_by_month,
    date_trunc('month'::text, (counters.measurement_start_day)::timestamp with time zone) AS month
   FROM public.counters
  WHERE (counters.measurement_start_day > (date_trunc('month'::text, now()) - '2 years'::interval))
  GROUP BY (date_trunc('month'::text, (counters.measurement_start_day)::timestamp with time zone))
  WITH NO DATA;

ALTER TABLE public.global_by_month OWNER TO shovel;

CREATE MATERIALIZED VIEW public.global_stats AS
 SELECT count(DISTINCT counters.probe_asn) AS network_count,
    count(DISTINCT counters.probe_cc) AS country_count,
    sum(counters.measurement_count) AS measurement_count
   FROM public.counters
  WITH NO DATA;

ALTER TABLE public.global_stats OWNER TO shovel;

CREATE TABLE public.jsonl (
    report_id text NOT NULL,
    input text,
    id integer,
    s3path text NOT NULL,
    linenum integer NOT NULL
);

ALTER TABLE public.jsonl OWNER TO shovel;

ALTER TABLE ONLY public.fastpath
    ADD CONSTRAINT fastpath_pkey PRIMARY KEY (measurement_uid);

ALTER TABLE ONLY public.counters_asn_noinput
    ADD CONSTRAINT unique_counters_asn_noinput_cell UNIQUE (measurement_start_day, test_name, probe_cc, probe_asn);

ALTER TABLE ONLY public.counters
    ADD CONSTRAINT unique_counters_cell UNIQUE (measurement_start_day, test_name, probe_cc, probe_asn, input);

ALTER TABLE ONLY public.counters_noinput
    ADD CONSTRAINT unique_counters_noinput_cell UNIQUE (measurement_start_day, test_name, probe_cc);

CREATE INDEX autoclavedlookup_idx ON public.autoclavedlookup USING hash (md5((report_id || COALESCE(input, ''::text))));

CREATE INDEX autoclavedlookup_report2_idx ON public.autoclavedlookup USING hash (report_id);

CREATE INDEX citizenlab_multi_idx ON public.citizenlab USING btree (url, domain, category_code, cc);

CREATE INDEX counters_asn_noinput_brin_multi_idx ON public.counters_asn_noinput USING brin (measurement_start_day, test_name, probe_cc, probe_asn, anomaly_count, confirmed_count, failure_count, measurement_count) WITH (pages_per_range='16');

CREATE INDEX counters_day_brin_idx ON public.counters USING brin (measurement_start_day) WITH (pages_per_range='4');

CREATE INDEX counters_day_cc_asn_input_idx ON public.counters USING btree (measurement_start_day, probe_cc, probe_asn, input);

CREATE INDEX counters_day_cc_brin_idx ON public.counters USING brin (measurement_start_day, probe_cc) WITH (pages_per_range='4');

CREATE INDEX counters_multi_brin_idx ON public.counters USING brin (measurement_start_day, test_name, probe_cc, probe_asn, input) WITH (pages_per_range='64');

CREATE INDEX counters_noinput_brin_multi_idx ON public.counters_noinput USING brin (measurement_start_day, test_name, probe_cc, anomaly_count, confirmed_count, failure_count, measurement_count) WITH (pages_per_range='32');

CREATE INDEX fastpath_multi_idx ON public.fastpath USING btree (measurement_start_time, probe_cc, test_name, domain);

CREATE INDEX fastpath_report_id_input_idx ON public.fastpath USING btree (report_id, input);

CREATE INDEX jsonl_lookup_idx ON public.jsonl USING btree (report_id, input, id);

CREATE INDEX measurement_start_time_btree_idx ON public.fastpath USING btree (measurement_start_time);

GRANT SELECT ON TABLE public.citizenlab TO readonly;
GRANT SELECT ON TABLE public.citizenlab TO "oomsm-beta";
GRANT SELECT ON TABLE public.citizenlab TO amsapi;

GRANT SELECT ON TABLE public.counters TO readonly;

GRANT SELECT ON TABLE public.fastpath TO readonly;
GRANT SELECT ON TABLE public.fastpath TO amsapi;
GRANT SELECT ON TABLE public.fastpath TO "oomsm-beta";
"""


def db_drop():
    """Drop database tables"""
    raise NotImplementedError


steps = (
    (db_setup, db_drop),
)

if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list steps")
    conf = ap.parse_args()

    if conf.list:
        for rf, rollback in steps:
            print(f"{rf.__name__} - {rf.__doc__}")
            print(f"  {rollback.__name__} - {rollback.__doc__}")
            print()
