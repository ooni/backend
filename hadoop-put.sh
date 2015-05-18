#!/bin/sh
REPORTS_BY_DATE_DIR=/data1/reports/
for report_file in `find $REPORTS_BY_DATE_DIR`;do
  hadoop fs -put $report_file /user/ooni/reports/
done
