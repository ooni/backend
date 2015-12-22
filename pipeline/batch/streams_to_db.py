import psycopg2
import os
import traceback
from datetime import datetime
from pipeline.helpers.util import get_luigi_target, json_loads
from pipeline.helpers.util import json_dumps, get_date_interval

from invoke.config import Config
config = Config(runtime_path="invoke.yaml")

class StreamToDb:
    columns = [
        ('id', 'UUID PRIMARY KEY DEFAULT gen_random_uuid()'),
        ('input', 'TEXT'),
        ('report_id', 'TEXT'),
        ('report_filename', 'TEXT'),
        ('options', 'JSONB'),
        ('probe_cc', 'TEXT'),
        ('probe_asn', 'TEXT'),
        ('probe_ip', 'TEXT'),
        ('data_format_version', 'TEXT'),
        ('test_name', 'TEXT'),
        ('test_start_time', 'TIMESTAMP'),
        ('test_runtime', 'REAL'),
        ('test_helpers', 'JSONB'),
        ('test_keys', 'JSONB'),
        ('software_name', 'TEXT'),
        ('software_version', 'TEXT'),
        ('test_version', 'TEXT')
    ]
    # there's got to be a better way to insert a row from a dictionary
    # keyed by the column names... insert_template should look like:
    # 'INSERT INTO reports (input, report_id, report_filename, options, \
    #  probe_cc, probe_asn, probe_ip, data_format_version, test_name, \
    #  test_start_time, test_runtime, test_helpers, test_keys) VALUES \
    #  (%(input)s, %(report_id)s, %(report_filename)s, %(options)s, \
    #  %(probe_cc)s, %(probe_asn)s, %(probe_ip)s, %(data_format_version)s, \
    #  %(test_name)s, %(test_start_time)s, %(test_runtime)s, %(test_helpers)s, \
    #  %(test_keys)s);'
    # then we can pass that template string to psycopg2 along with a dict
    # and it will do the interpolation/conversion.
    def __init__(self, stream):
        self.good_entries = 0
        self.bad_entries = 0

        self.stream = stream
        self.insert_entry_template = "INSERT INTO %s (" % str(config.postgres.table)
        self.insert_entry_template += ", ".join([col[0] for col in self.columns]) + ") "
        self.insert_entry_template += "VALUES ("
        self.insert_entry_template += ", ".join(["%%(%s)s" % col[0] for col in self.columns])
        self.insert_entry_template += ");"

        self.create_table_string = "CREATE TABLE %s (" % str(config.postgres.table)
        self.create_table_string += ", ".join("%s %s" % ct for ct in self.columns)
        self.create_table_string += ");"

    def format_record(self, entry):
        record = {}
        for (col_name, col_type) in self.columns:
            if col_name == 'test_keys': # this column gets a json_dump of whatever's left
                continue
            elif col_name == 'test_start_time': # Entry is actually called start_time
                try:
                    start_time = entry.pop('start_time')
                    test_start_time = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")
                except KeyError:
                    test_start_time = None
                record[col_name] = test_start_time
            elif col_type == 'JSONB':
                record[col_name] = json_dumps(entry.pop(col_name, None))
            else:
                record[col_name] = entry.pop(col_name, None)
        record['test_keys'] = json_dumps(entry)
        return record

    def failed_entry(self, record):
        self.bad_entries += 1
        print "FAILED"
        print self.format_record(record)
        print record
        print traceback.format_exc()

    def connect(self):
        self.conn = psycopg2.connect(host=str(config.postgres.host),
                                database=str(config.postgres.database),
                                user=str(config.postgres.username),
                                password=str(config.postgres.password))
        self.conn.autocommit = True

    def insert_entry(self, record):
        formatted_record = self.format_record(record)
        try:
            self.conn.cursor().execute(self.insert_template, formatted_record)
            self.good_entries += 1
        except psycopg2.DataError:
            try:
                for idx, request in enumerate(formatted_record['requests']):
                    formatted_record['requests'][idx]['response'].pop('body')
                    self.conn.cursor().execute(self.insert_template,
                                               formatted_record)
                    self.good_entries += 1
            except KeyError:
                pass
            except Exception:
                self.failed_entry(record)
        except Exception:
            self.failed_entry(record)

    def create_table(self):
        cur = self.conn.cursor()
        cur.execute("SELECT relname FROM pg_class WHERE relname='metrics';")
        if cur.rowcount == 0:
            self.conn.cursor().execute(self.create_table_string)

    def create_indexes(self):
        indexes = ["probe_cc", "input", "test_name"]
        for idx in indexes:
            try:
                # Tests for existence of the index: http://dba.stackexchange.com/a/35626
                self.conn.cursor().execute("SELECT 'public.%{idx}_idx'::regclass".format(idx=idx))
            except psycopg2.ProgrammingError:
                self.conn.cursor().execute("CREATE INDEX %{idx}_idx ON metrics (%{idx})".format(idx=idx))

    def update_views(self):
        try:
            self.conn.cursor().execute("SELECT 'public.country_counts_view'::regclass")
            self.conn.cursor().execute("REFRESH MATERIALIZED VIEW country_counts_view")
        except psycopg2.ProgrammingError:
            self.conn.cursor().execute('CREATE MATERIALIZED VIEW "country_counts_view" AS SELECT probe_cc, count(probe_cc) FROM metrics GROUP BY probe_cc;')

    def run(self):
        self.connect()
        self.create_table()
        try:
            for line in self.stream:
                record = json_loads(line.strip('\n'))
                if record["record_type"] == "entry":
                    self.insert_entry(record)
        finally:
            print "successful entries: %s" % self.good_entries
            print "failed entries: %s" % self.bad_entries
            self.create_indexes()
            self.update_views()
            self.conn.close()

def run(streams_dir, date_interval):
    interval = get_date_interval(date_interval)
    for date in interval:
        stream_path = os.path.join(streams_dir, date.isoformat() + ".json")
        try:
            stream_target = get_luigi_target(stream_path)
            with stream_target.open('r') as stream:
                StreamToDb(stream).run()
        except IOError:
            continue
        except Exception:
            print "failed: '%s'" % stream_path
            print traceback.format_exc()
        else:
            print "succeeded: '%s'" % stream_path
    print "done"
