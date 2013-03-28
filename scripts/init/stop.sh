#!/bin/sh
source /etc/mlab/slice-functions
cd $SLICEHOME
sudo -u $SLICENAME kill `cat $SLICEHOME/oonib.pid`
