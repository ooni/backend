from __future__ import print_function

from glob import glob
import os
from pyspark import SparkContext
from pyspark.sql import SQLContext

report_dir = "/data1/reports/"
output_dir = "/data1/processed/"
if __name__ == "__main__":
    sc = SparkContext(appName="PythonSQL")
    sqlContext = SQLContext(sc)

    def join_files(output_directory):
        output_file = open(output_directory + ".json", "w+")
        for file_path in sorted(glob(output_date_dir + "/part-*")):
            with open(file_path) as f:
                output_file.write(f.read())
        output_file.close()

    def list_reports():
        for filename in os.listdir(report_dir):
            if filename.endswith(".sanitised"):
                yield os.path.join(report_dir, filename)

    total_per_country = None
    for report_path in list_reports():
        output_date_dir = os.path.basename(report_path).replace(".sanitised", "")
        output_date_dir = os.path.join(output_dir, output_date_dir)

        reports = sqlContext.jsonFile(report_path)
        reports.select("record_type").show()

        per_country = reports.filter(reports.record_type == "header").groupBy("probe_cc").count()
        if total_per_country is None:
            total_per_country = per_country
        else:
            total_per_country.join(per_country)

        per_country.toJSON().saveAsTextFile(output_date_dir)
        join_files(output_date_dir)

    output_total_dir = os.path.join(output_dir, "total")
    total_per_country.toJSON().saveAsTextFile()
    join_files(output_total_dir)
