# Build: run ooni-sysadmin.git/scripts/docker-build from this directory

FROM ubuntu:16.04

# All the actions are done within single RUN to reduce number of layers & overall fetch size.
RUN set -ex \
    && apt-get update \
    && apt-get install -y python2.7 liblz4-tool python-ujson python-yaml python-psycopg2 python-six \
    && : \
# Whole python-lz4 repo is clonned as `git` can't do shallow clone of single
# SHA1 commit and github tarball makes setuptools-scm unhappy while building.
# lz4=0.8.2 from pip does not support LZ4 frame format yet.
    && apt-get install -y python-pkg-resources build-essential python-setuptools python-setuptools-scm git-core python2.7-dev \
    && git clone https://github.com/python-lz4/python-lz4.git /var/tmp/python-lz4 \
    && cd /var/tmp/python-lz4 \
    && git checkout -b build dc512f81f3d73069610ce33bb88abfff1fb2f96d \
    && python2.7 setup.py install --single-version-externally-managed --root=/ \
    && : \
# `pip` pollutes /root/.cache
    && apt-get install -y python-pip \
    && pip install --system mmh3==2.3.1 simhash-py==0.4.0 \
    && : \
# awscli in ubuntu has a bug that triggers following error message in `aws s3 cp`:
# upload failed: tmp/oo....yaml to s3://ooni-data/autoclaved/jsonl/2017-04-22/201...yaml seek() takes 2 positional arguments but 3 were given
# awscli is released DAILY and that's a bit scary, so pretty random "latest release" version is used
    && apt-get install -y python3-pip awscli \
    && pip3 install --system awscli==1.11.185 \
    && : \
    && apt-get install --no-install-recommends -y openssh-client rsync \
    && useradd -m ooshovel -u 1000 \
    && : \
    && apt-get remove --auto-remove -y \
            python-pkg-resources build-essential python-setuptools python-setuptools-scm git-core python2.7-dev \
            python-pip \
            python3-pip \
    && : \
    && rm -rf \
        /var/tmp/python-lz4 \
        /var/tmp/simhash-py \
        /var/lib/apt/lists \
        /root/.cache \
    && :

COPY canning.py daily_workflow.py autoclaving.py centrifugation.py originas2pg.py \
    aws_s3_ls.py \
    aws_s3_lz4cat_sync.py \
    delete_canned_report.py \
    cleanup_reports_raw.py \
    cleanup_uploaded.py \
    check_sanitised.py \
    cleanup_sanitised.py \
    canned_repeated.py \
    canned_gzip_index.py \
    tar_reports_raw.py \
    /usr/local/bin/

COPY oonipl /usr/local/lib/python2.7/dist-packages/oonipl

USER daemon
