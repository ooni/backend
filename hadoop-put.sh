#!/bin/sh
REPORTS_BY_DATE_DIR=/data1/reports/
for SRC_PATH in $( find $REPORTS_BY_DATE_DIR -name "*.sanitised" );do
  DST_PATH="/user/ooni/reports/sanitised/$(basename $SRC_PATH | sed s/\.sanitised//)"
  echo "Copying $SRC_PATH to hdfs://$DST_PATH"
  hadoop fs -put -f $SRC_PATH $DST_PATH
done
for SRC_PATH in $( find $REPORTS_BY_DATE_DIR -name "*.raw" );do
  DST_PATH="/user/ooni/reports/raw/$(basename $SRC_PATH | sed s/\.raw//)"
  echo "Copying $SRC_PATH to hdfs://$DST_PATH"
  hadoop fs -put -f $SRC_PATH $DST_PATH
done
