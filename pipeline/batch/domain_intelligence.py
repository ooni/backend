import re
import os
import csv
import tempfile
import zipfile

from six.moves.urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests
import luigi

from .sql_tasks import RunQuery

config = luigi.configuration.get_config()


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


def get_url_category(url, test_lists_directory):
    results = []
    test_lists = filter(lambda x: x.endswith(".csv") and not x.startswith("00-"),
                        os.listdir(test_lists_directory))
    for test_list in test_lists:
        country_code = test_list.replace(".csv", "").upper()
        file_path = os.path.join(test_lists_directory, test_list)
        with open(file_path) as f:
            reader = csv.reader(f)
            reader.next()
            for row in reader:
                this_url, category_code, category_description, \
                    date_added, source, notes = row
                if url == this_url:
                    results.append((category_code, category_description, country_code))
    return results

def get_url_alexa_ranking(url):
    hostname = urlparse(url).hostname
    r = requests.get("http://www.alexa.com/siteinfo/{}".format(hostname))
    soup = BeautifulSoup(r.text)
    return soup.find("span", {"data-cat": "globalRank"}).find("strong", {"class": "metrics-data"}).text.strip()


def get_number_of_google_results(url):
    # XXX It's important to ensure that this get's run very slowly
    hostname = urlparse(url).hostname
    r = requests.get("https://www.google.com/search?q=%22{}%22".format(hostname))
    soup = BeautifulSoup(r.text)
    result_stats = soup.find("div", {"id": "resultStats"}).text
    results = re.search("[A-Za-z]+ ((\d+\.)+\d+) [a-z]+", result_stats).group(1)
    return int(results.replace(".", ""))

class UpdatePostgres(luigi.postgres.CopyToTable):
    host = config.get("postgres", "host")
    database = config.get("postgres", "database")
    user = config.get("postgres", "user")
    password = config.get("postgres", "password")

class ListDomainsInPostgres(RunQuery):
    table = config.get("postgres", "metrics-table")

    def query(self):
        return """SELECT DISTINCT input FROM {metrics_table}
    WHERE test_name='dns_consistency'
        OR test_name='http_requests'
        OR test_name='http_host'
""".format(metrics_table=self.table)

class ListASNSInPostgres(RunQuery):
    table = config.get("postgres", "metrics-table")

    def query(self):
        return """SELECT DISTINCT probe_asn FROM
    {metrics_table}""".format(metrics_table=self.table)

class UpdateDomainsPostgres(UpdatePostgres):
    table = config.get("postgres", "domain-table", "domains")

    def requires(self):
        pass

class UpdateASNPostgres(UpdatePostgres):
    table = config.get("postgres", "asn-table", "asns")

    columns = [
        ('id', 'UUID PRIMARY KEY'),
        ('asn', 'TEXT'),
        ('provider_name', 'TEXT'),
        ('provider_alt_name', 'TEXT'),
        ('provider_website', 'TEXT'),
        ('provider_type', 'TEXT'),
        ('update_time', 'TIMESTAMP')
    ]
