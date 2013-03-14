#!/bin/sh

source /etc/mlab/slice-functions
cd $SLICEHOME
bin/oonib -c $SLICEHOME/oonib.conf &
