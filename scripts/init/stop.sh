#!/bin/sh
source /etc/mlab/slice-functions
cd $SLICEHOME
kill `cat $HOME/oonib.pid`
