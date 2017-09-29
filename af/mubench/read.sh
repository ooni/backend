#!/bin/sh

python -m timeit --repeat 20 --setup 'from tarfile_read import main_tarpipe, main_craftpipe, nop, readblob, readlines' -- 'main_craftpipe(readlines)'

for main in main_tarpipe main_craftpipe; do
    for process in nop readblob readlines; do
        (
        set -o xtrace
        python -m timeit --repeat 20 --setup 'from tarfile_read import main_tarpipe, main_craftpipe, nop, readblob, readlines' -- "${main}(${process})"
        )
    done
done

