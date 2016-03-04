import re
import os
import csv
import time
import zipfile
import logging
import datetime
import tempfile
import subprocess

from six.moves.urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests

import luigi
from luigi.postgres import PostgresTarget

from .sql_tasks import RunQuery

config = luigi.configuration.get_config()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('ooni-pipeline')


def download_citizen_lab_test_list():
    archive_url = "https://github.com/citizenlab/test-lists/archive/master.zip"
    output_directory = tempfile.mkdtemp()

    r = requests.get(archive_url, stream=True)
    with tempfile.NamedTemporaryFile(delete=False) as fw:
        zip_filename = fw.name
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                fw.write(chunk)

    with open(zip_filename, 'rb') as f:
        z = zipfile.ZipFile(f)
        z.extractall(output_directory)
    os.remove(zip_filename)

    return os.path.join(output_directory, 'test-lists-master', 'lists')


def list_urls(test_lists_directory):
    test_lists = filter(lambda x: x.endswith(".csv") and not x.startswith("00-"),
                        os.listdir(test_lists_directory))
    for test_list in test_lists:
        country_code = test_list.replace(".csv", "").upper()
        file_path = os.path.join(test_lists_directory, test_list)
        with open(file_path) as f:
            reader = csv.reader(f)
            reader.next()
            for row in reader:
                yield row + [country_code]

def get_url_category(url, test_lists_directory):
    results = []
    for row in list_urls(test_lists_directory):
        this_url, category_code, category_description, \
            date_added, source, notes, country_code = row
        if url == this_url:
            results.append((category_code, category_description, country_code))
    return results


def get_url_alexa_ranking(url):
    hostname = urlparse(url).hostname
    r = requests.get("http://www.alexa.com/siteinfo/{}".format(hostname))
    soup = BeautifulSoup(r.text)
    ranking = soup.find("span", {"data-cat": "globalRank"}).find("strong", {"class": "metrics-data"}).text.strip()
    ranking = ranking.replace(",", "").replace(".", "")
    if ranking == '-':
        ranking = 0
    logger.debug("This is the ranking {}: {}".format(hostname, ranking))
    return int(ranking)


class GoogleCAPTCHAError(Exception):
    pass

def get_number_of_google_results(url):
    # XXX It's important to ensure that this get's run very slowly
    hostname = urlparse(url).hostname
    r = requests.get("https://www.google.com/search?q=%22{}%22".format(hostname))
    soup = BeautifulSoup(r.text)
    if soup.find("form", {"action": "CaptchaRedirect"}) is not None:
        raise GoogleCAPTCHAError
    result_stats = soup.find("div", {"id": "resultStats"}).text
    logger.debug("Results stats: {}".format(result_stats))
    results = re.search("[A-Za-z]*\s*((\d+[\.,]?)+\d+) [a-z]+", result_stats).group(1)
    return int(results.replace(".", ""))


class UpdatePostgres(luigi.postgres.CopyToTable):
    host = config.get("postgres", "host")
    database = config.get("postgres", "database")
    user = config.get("postgres", "user")
    password = config.get("postgres", "password")


class DumpPostgresQuery(RunQuery):
    table = config.get("postgres", "metrics-table")

    def run(self):
        dst_target = self.output()['dst'].open('w')
        connection = self.output()['src'].connect()
        cursor = connection.cursor()
        sql = self.query()

        cursor.execute(sql)
        while True:
            row = cursor.fetchone()
            if row is None:
                break
            data = self.format_row(row)
            if not data:
                continue
            dst_target.write(data)

        self.output()['src'].touch(connection)

        connection.commit()
        connection.close()
        dst_target.close()

    def format_row(self, row):
        raise NotImplemented("You must implement this with a method that returns the string to be written to the target")

    @property
    def dst_target(self):
        raise NotImplemented("You must implement this with a custom target")

    def output(self):
        return {
            'src': PostgresTarget(
                host=self.host,
                database=self.database,
                user=self.user,
                password=self.password,
                table=self.table,
                update_id=self.update_id
                ),
            'dst': self.dst_target
        }

class ListDomainsInPostgres(DumpPostgresQuery):
    update_date = luigi.DateParameter(default=datetime.date.today())

    def query(self):
        return """SELECT DISTINCT input FROM {metrics_table}
    WHERE test_name='dns_consistency'
        OR test_name='http_requests'
        OR test_name='http_host'
""".format(metrics_table=self.table)

    def format_row(self, row):
        url = row[0]
        if not url:
            return url
        if not url.startswith("http"):
            url = "http://{}".format(url)
        return "{}\n".format(url)

    @property
    def dst_target(self):
        return luigi.LocalTarget(self.update_date.strftime("/tmp/domains-%Y-%m-%d.txt"))


class ListCitizenLabURLS(luigi.ExternalTask):
    update_date = luigi.DateParameter(default=datetime.date.today())
    cooldown = 2

    def output(self):
        return luigi.LocalTarget(self.update_date.strftime("/tmp/domains-citizenlab-%Y-%m-%d.tsv"))

    def get_google_results(self, url):
        if url in self.google_results.keys():
            return self.google_results[url]
        if (time.time() - self._last_request_google < self.cooldown):
            logger.debug("Cooling down with google")
            time.sleep(self.cooldown)
        self._last_request_google = time.time()
        self.google_results[url] = get_number_of_google_results(url)
        return self.google_results[url]

    def get_alexa_ranking(self, url):
        hostname = urlparse(url).hostname
        if hostname in self.alexa_ranks.keys():
            return self.alexa_ranks[hostname]
        if (time.time() - self._last_request_alexa < self.cooldown):
            logger.debug("Cooling down with alexa")
            time.sleep(self.cooldown)
        self._last_request_alexa = time.time()
        self.alexa_ranks[hostname] = get_url_alexa_ranking(url)
        return self.alexa_ranks[hostname]

    def run(self):
        test_lists_directory = download_citizen_lab_test_list()
        out_file = self.output().open('w')

        self.alexa_ranks = {}
        self.google_results = {}

        self._last_request_google = time.time()
        self._last_request_alexa = time.time()

        for row in list_urls(test_lists_directory):
            url, category_code, category_description, \
                date_added, source, notes, country_code = row
            alexa_ranking = -1
            # XXX we temporarily disable alexa and google since we were triggering
            # anti-crawler banning
            # try:
            #     alexa_ranking = self.get_alexa_ranking(url)
            # except Exception as exc:
            #     logger.error("Failed to lookup {} on alexa".format(url))
            #     logger.error(exc)
            google_results = -1
            # try:
            #     google_results = self.get_google_results(url)
            # except Exception as exc:
            #     logger.error("Failed to lookup {} on google".format(url))
            #     logger.error(exc)
            out_file.write("{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n".format(
                url, category_code, category_description,
                date_added, source, country_code, alexa_ranking,
                google_results, self.update_date
            ))
        out_file.close()

class InsertCitizenLabURLS(UpdatePostgres):
    table = config.get("postgres", "domain-table", "domains")
    update_date = luigi.DateParameter(default=datetime.date.today())

    columns = [
        ('url', 'TEXT'),
        ('category_code', 'TEXT'),
        ('category_description', 'TEXT'),
        ('date_added', 'DATE'),
        ('source', 'TEXT'),
        ('country_code', 'TEXT'),
        ('alexa_ranking', 'INT'),
        ('google_results', 'INT'),
        ('update_date', 'DATE')
    ]

    def init_copy(self, connection):
        query = "TRUNCATE TABLE {table};".format(table=self.table)
        connection.cursor().execute(query)

    def requires(self):
        return ListCitizenLabURLS(update_date=self.update_date)


class ListASNSInPostgres(DumpPostgresQuery):
    update_date = luigi.DateParameter(default=datetime.date.today())

    def query(self):
        return """SELECT DISTINCT probe_asn FROM
    {metrics_table}""".format(metrics_table=self.table)

    def format_row(self, row):
        asn = row[0]
        if not asn:
            return asn
        return "{}\n".format(asn)

    @property
    def dst_target(self):
        return luigi.LocalTarget(self.update_date.strftime("/tmp/asns-%Y-%m-%d.txt"))


class ASNNotFound(Exception):
    pass

class GetASNInformation(luigi.Task):
    update_date = luigi.DateParameter(default=datetime.date.today())

    def requires(self):
        return ListASNSInPostgres(update_date=self.update_date)

    def output(self):
        return luigi.LocalTarget(self.update_date.strftime("/tmp/asn-information-%Y-%m-%d.tsv"))

    def get_asn_information(self, asn):
        domain = "{}.asn.cymru.com".format(asn)
        args = ['dig', '+short', domain, 'TXT']
        proc = subprocess.Popen(
                        args,
                        stdout=subprocess.PIPE)
        results = proc.communicate()[0]
        if results == '':
            raise ASNNotFound()
        results = results.replace('"', '')
        return map(lambda x: x.strip(), results.split("|"))[1:]

    def run(self):
        out_file = self.output().open('w')
        with self.input()['dst'].open('r') as in_file:
            for asn in in_file:
                asn = asn.strip()
                try:
                    country_code, registry, \
                        source_updated, name = self.get_asn_information(asn)
                except ASNNotFound:
                    logger.error("Could not find {}".format(asn))
                    continue
                if source_updated == "":
                    source_updated = "1970-01-01"
                out_file.write("{}\t{}\t{}\t{}\t{}\t{}\n".format(
                    asn, country_code, registry,
                    source_updated, name, self.update_date
                ))
        out_file.close()

class UpdateASNPostgres(UpdatePostgres):
    table = config.get("postgres", "asn-table", "asns")

    update_date = luigi.DateParameter(default=datetime.date.today())

    columns = [
        ('asn', 'TEXT'),
        ('country_code', 'TEXT'),
        ('registry', 'TEXT'),
        ('source_update_date', 'TIMESTAMP'), # When it was updated according to team cymru
        ('name', 'TEXT'),
        ('update_date', 'TIMESTAMP') # When we updated this record last
    ]

    def init_copy(self, connection):
        query = "TRUNCATE TABLE {table};".format(table=self.table)
        connection.cursor().execute(query)

    def requires(self):
        return GetASNInformation(self.update_date)
