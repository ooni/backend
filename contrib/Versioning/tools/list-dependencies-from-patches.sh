#!/bin/bash

# Simple tool to list dependencies in form suitable for tsort utility.
# Run this script like this:
#   /some/path/list-dependencies-from-patches.sh *.sql | tsort | tac
# To get patches in order that satisfies dependencies while loading them.

grep -hiE '^[[:space:]]*select _v.register_patch\(' "$@" | \
    sed 's/^[^(]*(//' | while read LINE
    do
        export PATCH_NAME="$( echo "$LINE" | cut -d\' -f2 )"
        echo "$LINE" | sed "s/^[^']*'[^']\\+'[[:space:]]*,[[:space:]]*//" | \
            perl -ne '
                my @w;
                if ( s/^ARRAY\s*\[// ) {
                    s/\].*//;
                    @w = /\047([^\047]+)\047/g;
                }
                push @w, $ENV{"PATCH_NAME"} if ( 0 == @w ) || ( 0 == ( @w % 2 ) );
                printf "%s %s\n", $ENV{"PATCH_NAME"}, $_ for @w;
            '
    done
