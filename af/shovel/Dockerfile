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
    && cd / \
    && :

RUN set -ex \
    && apt-get remove --auto-remove -y python-pkg-resources build-essential python-setuptools python-setuptools-scm git-core python2.7-dev \
    && rm -rf /var/tmp/python-lz4 \
    && :

COPY canning.py /usr/local/bin/
COPY daily_workflow.py autoclaving.py /usr/local/bin/

USER daemon
