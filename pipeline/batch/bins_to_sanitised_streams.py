import os
import json
import traceback

from multiprocessing import Pool

from invoke.config import Config

from pipeline.helpers.report import Report
from pipeline.helpers.util import json_dumps, get_date_interval
from pipeline.helpers.util import list_report_files, get_luigi_target

config = Config(runtime_path="invoke.yaml")


class SanitiseAndAggregateBin():
    def __init__(self, bin_dir, sanitised_stream_path, bridge_db):
        self.bin_dir = bin_dir
        self.sanitised_stream_path = sanitised_stream_path
        self.bridge_db = bridge_db

    def run(self):
        sanitised_stream = get_luigi_target(self.sanitised_stream_path)
        with sanitised_stream.open('w') as sanitised_stream:

            for filename in list_report_files(self.bin_dir,
                                            config.aws.access_key_id,
                                            config.aws.secret_access_key):
                input_file = get_luigi_target(filename)
                with input_file.open('r') as in_file:
                    report = Report(in_file, self.bridge_db, input_file.path)
                    for sanitised_entry, _ in report.entries():
                        sanitised_stream.write(json_dumps(sanitised_entry))
                        sanitised_stream.write("\n")

def wrapAggregator(bin_dir, sanitised_dir, bridge_db):
    try:
        print "starting '%s' -> '%s'" % (bin_dir, sanitised_dir)
        SanitiseAndAggregateBin(bin_dir, sanitised_dir, bridge_db).run()
    except Exception:
        print "failed '%s' -> '%s'" % (bin_dir, sanitised_dir)
        print traceback.format_exc()
    else:
        print "success '%s' -> '%s'" % (bin_dir, sanitised_dir)

# unsanitised_dir: private
# sanitised_dir: public
# |-- private
# |   `-- yaml
# |       |-- 2012-01-01
# |       |   `-- 20130506T022124Z-AS24173-http_header_field_manipulation-v1-probe.yaml
# |       `-- 2012-01-02
# `-- public
#     `-- json
#         |-- 2012-01-01.json
#         `-- 2012-01-02.json

def run(unsanitised_dir, sanitised_dir, date_interval, workers):
    p = Pool(processes=int(workers))

    with get_luigi_target(config.ooni.bridge_db_path).open('r') as f:
        bridge_db = json.load(f)

    interval = get_date_interval(date_interval)
    for date in interval:
        bin_dir = os.path.join(unsanitised_dir, 'yaml', date.isoformat())
        sanitised_stream_path = os.path.join(sanitised_dir,
                                             'json', "%s.json" % date.isoformat())
        print "queueing '%s' -> '%s'" % (bin_dir, sanitised_stream_path)
        p.apply_async(wrapAggregator, args=(bin_dir, sanitised_stream_path, bridge_db))
    p.close()
    p.join()

