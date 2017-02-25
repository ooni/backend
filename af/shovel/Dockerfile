# BUILD: docker build --rm -t ooni/shovel .

FROM ubuntu:16.04

RUN set -ex \
    && apt-get update \
    && apt-get install -y python2.7 liblz4-tool python-ujson python-yaml \
    && :

# Whole python-lz4 repo is clonned as `git` can't do shallow clone of single
# SHA1 commit and github tarball makes setuptools-scm unhappy while building.
# lz4=0.8.2 from pip does not support LZ4 frame format yet.
RUN set -ex \
    && apt-get install -y python-pkg-resources build-essential python-setuptools python-setuptools-scm git-core python2.7-dev \
    && git clone https://github.com/python-lz4/python-lz4.git /var/tmp/python-lz4 \
    && cd /var/tmp/python-lz4 \
    && git checkout -b build dc512f81f3d73069610ce33bb88abfff1fb2f96d \
    && python2.7 setup.py install --single-version-externally-managed --root=/ \
    && :

# Cython simhash, tag: v0.3.0, python-six is dependency, not build-dep
RUN set -ex \
    && apt-get install -y python-six \
    && git clone https://github.com/seomoz/simhash-py.git /var/tmp/simhash-py \
    && cd /var/tmp/simhash-py \
    && git checkout -b build 79bd4044f046c5542aee8e72849932f9e5d65403 \
    && git submodule update --init --recursive \
    && python2.7 setup.py install \
    && :

# `pip` pollutes /root/.cache
RUN set -ex \
    && apt-get install -y python-pip \
    && pip install --system mmh3==2.3.1 \
    && apt-get remove --auto-remove -y python-pip \
    && :

RUN set -ex \
    && apt-get remove --auto-remove -y python-pkg-resources build-essential python-setuptools python-setuptools-scm git-core python2.7-dev \
    && rm -rf \
        /var/tmp/python-lz4 \
        /var/tmp/simhash-py \
        /var/lib/apt/lists \
        /root/.cache \
    && :

COPY canning.py daily_workflow.py autoclaving.py centrifugation.py /usr/local/bin/

USER daemon
