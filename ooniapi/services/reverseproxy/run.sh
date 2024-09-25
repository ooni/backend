#!/bin/bash
set -ex

docker run -p 8080:80 --rm -it $(docker build -q .)
