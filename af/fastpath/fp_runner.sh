#!/bin/bash
#
# Runs the fastpath from CLI using GNU parallel
# debdeps: parallel

export START_DAY="2014-11-1"
export DAYS=1
export PARALLEL_JOBS=4

runfp() {
  since=$(date -d "$START_DAY +$1 days - 1 days" +%Y-%m-%d)
  until=$(date -d "$START_DAY +$1 days" +%Y-%m-%d)
  fastpath --start-day=$since --end-day=$until --noapi --devel
  #fastpath --start-day=$since --end-day=$until --noapi --devel --update
}
export -f runfp
parallel -v -j$PARALLEL_JOBS --eta --ungroup runfp ::: $(seq $DAYS)
