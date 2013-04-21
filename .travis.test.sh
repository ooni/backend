#!/bin/bash
##############################################################################
#
# .travis.test.sh
# -------------------
# Run $2 for $1 seconds and then kill the process.
#
# :authors: Isis Agora Lovecruft, 0x2cdb8b35
# :date: 21 April 2013
# :version: 0.0.1
##############################################################################

function killitwithfire () {
    trap - ALRM
    kill -ALRM $prog 2>/dev/null
    kill $! 2>/dev/null && exit 124
}

function waitforit () {
    trap "killitwithfire" ALRM
    sleep $1 & wait
    kill -ALRM $$
}

waitforit $1& prog=$! ; shift ;
trap "killitwithfire" ALRM INT
"$@"& wait `cat oonib.pid`
RET=$?
kill -ALRM $prog
wait $prog
exit $RET
