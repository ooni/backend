#!/bin/sh

source /etc/mlab/slice-functions
cd $SLICEHOME
sudo -u $SLICENAME bin/oonib -c $SLICEHOME/oonib.conf &
