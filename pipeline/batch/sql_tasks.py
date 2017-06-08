# -*- coding: utf-8 -*-

from datetime import datetime
import luigi
from luigi.postgres import PostgresTarget

config = luigi.configuration.get_config()

# These are the countries for which we identify blocking by looking for certain
# fingerprint in the HTTP response body.
blockpage_body_fingerprints = {
    'IR': '%iframe src="http://10.10%',
    'TR': '%<title>Telekomünikasyon İletişim Başkanlığı</title>%',
    'GR': '%www.gamingcommission.gov.gr/index.php/forbidden-access-black-list/%',
    'RU': '%http://eais.rkn.gov.ru/%',
    'IN': '%The page you have requested has been blocked%',
    'BE': '%that is considered illegal according to Belgian legislation%',
    'IT': '%GdF Stop Page%',
    'CY': '%nba.com.cy/Eas/eas.nsf/All/6F7F17A7790A55C8C2257B130055C86F%',
    'DK': '%lagt at blokere for adgang til siden.%',
    'FR': '%xtpage = "page-blocage-terrorisme"%',
    'KR': '%http://warning.or.kr%',
    'RO': '%Accesul dumneavoastră către acest site a fost restricționat%'
}

# These are countries for which we detect blocking by looking for certain
# header values.
blockpage_header_fingerprints = {
    'SA': ('Server', 'Protected by WireFilter%'),
    'ID': ('Location', 'http://internet-positif.org%'),
    'SD': ('Location', 'http://196.1.211.6:8080/alert/'),
    'QA': ('Location', 'http://www.vodafone.qa/alu.cfm'),
    'KR': ('Location', 'http://www.warning.or.kr'),
    'PT': ('Location', 'http://mobilegen.vodafone.pt/denied/dn'),
    'NO': ('Location', 'http://block-no.altibox.net/'),
    'UK': ('Location', 'http://blocked.nb.sky.com%'),
    'RU': ('Location', 'http://warning.rt.ru%')
}

# These are countries for which blocking is identified by checking if the
# experiment measurement has failed while the control succeeds.
blockpage_failures = ('CN',)

where_body_template = {
    "http_requests": """({metrics_table}.test_keys -> 'requests' -> 0 -> 'response' ->> 'body'
            LIKE '{body_filter}' OR
        {metrics_table}.test_keys -> 'requests' -> 1 -> 'response' ->> 'body'
            LIKE '{body_filter}')
""",
    "web_connectivity": """
    array_length(
        ARRAY(SELECT * FROM json_array_elements(
                ({metrics_table}.test_keys->'requests')::json
              ) WHERE
                value->'response'->>'body' LIKE '{body_filter}'), 1) > 0
"""
}

where_header_template = {
    "http_requests": """{metrics_table}.test_keys -> 'requests' -> 0 -> 'response'
    -> 'headers' ->> '{header_name}' LIKE '{header_value}'
""",
    "web_connectivity": """ array_length(
        ARRAY(SELECT * FROM json_array_elements(
                ({metrics_table}.test_keys->'requests')::json
              ) WHERE value -> 'response'
                    -> 'headers'->> '{header_name}' LIKE '{header_value}'), 1) > 0
"""
}

where_failure_template = {
    "http_requests": """test_keys->'experiment_failure'!='null'
AND test_keys->'control_failure'='null'""",
    "web_connectivity": """test_keys->'experiment_failure'!='null'
AND test_keys->'control_failure'='null'"""
}
def select_block_count(probe_cc, where, metrics_table, **kwargs):
    query = """SELECT blocked.block_count,
    total.total_count,
    blocked.report_id,
    blocked.test_start_time,
    blocked.probe_cc,
    blocked.probe_asn
   FROM (SELECT count({metrics_table}.input) AS block_count,
            {metrics_table}.report_id,
            {metrics_table}.test_start_time,
            {metrics_table}.probe_cc,
            {metrics_table}.probe_asn
           FROM {metrics_table}
           WHERE {metrics_table}.probe_cc = '{probe_cc}'
                 AND (
"""
    sub_queries = []
    for test_name in ["http_requests", "web_connectivity"]:
        sub_query = "{metrics_table}.test_name = '"
        sub_query += test_name
        sub_query += "' AND "
        sub_query += where[test_name]
        sub_queries.append(sub_query)
    query += "OR ".join(sub_queries) + ")"

    query += """
          GROUP BY {metrics_table}.report_id, {metrics_table}.test_start_time,
                   {metrics_table}.probe_cc, {metrics_table}.probe_asn) blocked
     JOIN (SELECT count({metrics_table}.input) AS total_count,
            {metrics_table}.report_id
           FROM {metrics_table}
          WHERE {metrics_table}.probe_cc = '{probe_cc}' AND
                (
                    {metrics_table}.test_name = 'http_requests' OR
                    {metrics_table}.test_name = 'web_connectivity'
                )
          GROUP BY {metrics_table}.report_id) total ON
                total.report_id = blocked.report_id
    """
    return query.format(probe_cc=probe_cc,
                        metrics_table=metrics_table,
                        **kwargs)

def select_block_urls(probe_cc, where, metrics_table, **kwargs):
    query = """SELECT input, report_id,
        test_start_time,
        probe_cc,
        probe_asn
    FROM {metrics_table}
    WHERE {metrics_table}.probe_cc = '{probe_cc}'
        AND (
    """

    sub_queries = []
    for test_name in ["http_requests", "web_connectivity"]:
        sub_query = "{metrics_table}.test_name = '"
        sub_query += test_name
        sub_query += "' AND "
        sub_query += where[test_name]
        sub_queries.append(sub_query)
    query += "OR ".join(sub_queries) + ")"

    return query.format(probe_cc=probe_cc,
                        metrics_table=metrics_table,
                        **kwargs)

def create_blockpage_view(query_function, view_name, metrics_table):
    select_queries = []

    for probe_cc, body_filter in blockpage_body_fingerprints.items():
        select_queries.append(query_function(probe_cc=probe_cc,
                                             where=where_body_template,
                                             body_filter=body_filter,
                                             metrics_table=metrics_table))

    for probe_cc, headers in blockpage_header_fingerprints.items():
        header_name, header_value = headers
        select_queries.append(query_function(probe_cc=probe_cc,
                                             where=where_header_template,
                                             header_name=header_name,
                                             header_value=header_value,
                                             metrics_table=metrics_table))

    for probe_cc in blockpage_failures:
        select_queries.append(query_function(probe_cc=probe_cc,
                                             where=where_failure_template,
                                             metrics_table=metrics_table))

    query = 'CREATE MATERIALIZED VIEW "{view_name}" AS '.format(view_name=view_name)
    query += '\n\nUNION\n\n'.join(select_queries)
    query += ';\n\n'
    return query

def blockpage_count(metrics_table):
    return create_blockpage_view(query_function=select_block_count,
                                 view_name="blockpage_count",
                                 metrics_table=metrics_table)

def blockpage_urls(metrics_table):
    return create_blockpage_view(query_function=select_block_urls,
                                 view_name="blockpage_urls",
                                 metrics_table=metrics_table)

def identified_vendors(metrics_table):
    return """
CREATE MATERIALIZED VIEW "identified_vendors" AS  SELECT {metrics_table}.test_start_time,
    {metrics_table}.probe_cc,
    {metrics_table}.probe_asn,
    {metrics_table}.report_id,
    'bluecoat' AS vendor
   FROM {metrics_table}
  WHERE {metrics_table}.test_name = 'http_header_field_manipulation'
        AND {metrics_table}.test_keys -> 'tampering' -> 'header_name_diff' @> '["X-BlueCoat-Via"]'::jsonb
UNION
 SELECT {metrics_table}.test_start_time,
    {metrics_table}.probe_cc,
    {metrics_table}.probe_asn,
    {metrics_table}.report_id,
    'squid' AS vendor
   FROM {metrics_table}
  WHERE {metrics_table}.test_name = 'http_invalid_request_line'
        AND {metrics_table}.test_keys -> 'tampering' = 'true'
        AND ({metrics_table}.test_keys -> 'received' ->> 0
                LIKE '%squid%'::text
            OR {metrics_table}.test_keys -> 'received' ->> 1
                LIKE '%squid%'
            OR {metrics_table}.test_keys -> 'received' ->> 2
                LIKE '%squid%'
            OR {metrics_table}.test_keys -> 'received' ->> 3
                LIKE '%squid%')
UNION
 SELECT {metrics_table}.test_start_time,
    {metrics_table}.probe_cc,
    {metrics_table}.probe_asn,
    {metrics_table}.report_id,
    'privoxy' AS vendor
   FROM {metrics_table}
  WHERE {metrics_table}.test_name = 'http_invalid_request_line'
        AND {metrics_table}.test_keys -> 'tampering' = 'true'
        AND ({metrics_table}.test_keys -> 'received' ->> 0
                LIKE '%Privoxy%'::text
            OR {metrics_table}.test_keys -> 'received' ->> 1
                LIKE '%Privoxy%'
            OR {metrics_table}.test_keys -> 'received' ->> 2
                LIKE '%Privoxy%'
            OR {metrics_table}.test_keys -> 'received' ->> 3
                LIKE '%Privoxy%')

;
""".format(metrics_table=metrics_table)

def country_counts(metrics_table):
    return """CREATE MATERIALIZED VIEW "country_counts_view" AS SELECT probe_cc,
    count(probe_cc) FROM metrics GROUP BY probe_cc;""".format(metrics_table=metrics_table)

class RunQuery(luigi.Task):
    host = config.get("postgres", "host")
    database = config.get("postgres", "database")
    user = config.get("postgres", "user")
    password = config.get("postgres", "password")

    @property
    def update_id(self):
        return '{}(nonce={})'.format(
            self.task_family,
            datetime.now().strftime("%Y%m%d%H%m%s")
        )

    def run(self):
        connection = self.output().connect()
        cursor = connection.cursor()
        sql = self.query()

        cursor.execute(sql)

        self.output().touch(connection)

        connection.commit()
        connection.close()

    def output(self):
        return PostgresTarget(
            host=self.host,
            database=self.database,
            user=self.user,
            password=self.password,
            table=self.table,
            update_id=self.update_id
        )

class CreateBlockpageCountView(RunQuery):
    table = 'metrics-materialised-views'
    drop = luigi.BoolParameter()

    def query(self):
        metrics_table = config.get("postgres", "metrics-table")
        query = ""
        if self.drop == True:
            query += "DROP MATERIALIZED VIEW IF EXISTS blockpage_count;"
        query += blockpage_count(metrics_table)
        return query


class CreateBlockpageUrlsView(RunQuery):
    table = 'metrics-materialised-views'
    drop = luigi.BoolParameter()

    def query(self):
        metrics_table = config.get("postgres", "metrics-table")
        query = ""
        if self.drop == True:
            query += "DROP MATERIALIZED VIEW IF EXISTS blockpage_urls;"
        query += blockpage_urls(metrics_table)
        return query

class CreateIdentifiedVendorsView(RunQuery):
    table = 'metrics-materialised-views'
    def query(self):
        metrics_table = config.get("postgres", "metrics-table")
        return identified_vendors(metrics_table)

class CreateCountryCountsView(RunQuery):
    table = 'metrics-materialised-views'
    def query(self):
        metrics_table = config.get("postgres", "metrics-table")
        return country_counts(metrics_table)

class UpdateBlockpageFingerprints(luigi.WrapperTask):
    def requires(self):
        return [
            CreateBlockpageCountView(drop=True),
            CreateBlockpageUrlsView(drop=True)
        ]

class CreateMaterialisedViews(luigi.WrapperTask):
    def complete(self):
        return False

    def requires(self):
        return [
            CreateBlockpageCountView(),
            CreateBlockpageUrlsView(),
            CreateIdentifiedVendorsView(),
            CreateCountryCountsView()
        ]

class CreateIndexes(RunQuery):
    # This value is actually only used as a token to update the marker table.
    table = 'metrics-indexes'

    index_keys = ('probe_cc', 'input', 'test_start_time',
                  'test_name', 'report_id')

    def query(self):
        sql = ''
        for index_key in self.index_keys:
            sql += 'CREATE INDEX {index_key}_idx ON metrics ({index_key});\n'.format(
                 index_key=index_key
            )
        sql += 'CREATE INDEX test_start_time_probe_cc_idx ON metrics (test_start_time DESC, probe_cc);'
        return sql

if __name__ == "__main__":
    print blockpage_count("metrics")
    print blockpage_urls("metrics")
