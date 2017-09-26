# XXX we may want in the future to use a more minimal base image
FROM debian:jessie

ENV OONIBACKEND_VERSION '1.3.4'

# Add Tor PGP key
RUN set -x \
    && gpg --keyserver pool.sks-keyservers.net --recv A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89 \
    && gpg --export A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89 | apt-key add - \
    && echo "deb http://deb.torproject.org/torproject.org jessie main" \
         | tee /etc/apt/sources.list.d/tor.list

# Install tor and required dependencies
RUN set -x \
    && apt-get -y update \
    && apt-get install -y git-core python-pip python-dev libsqlite3-dev \
                       libffi-dev tor deb.torproject.org-keyring libdumbnet-dev

# Upgrade pip and setuptools to modern versions
RUN set -x \
    && pip install -U pip setuptools

RUN set -x \
    && mkdir /app

COPY ./dist/oonibackend-$OONIBACKEND_VERSION.tar.gz /tmp/

RUN set -x \
    && pip /tmp/oonibackend-$OONIBACKEND_VERSION.tar.gz
