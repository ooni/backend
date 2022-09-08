#!/bin/bash
#
# WARNING: run only in a dedicated container
# Prepares a container to run the API
# Called from spawnrunner or docker
#
set -eu
export DEBIAN_FRONTEND=noninteractive

echo 'deb http://deb.debian.org/debian bullseye-backports main' \
  > /etc/apt/sources.list.d/backports.list

# Install ca-certificates and gnupg first
apt-get update
apt-get install --no-install-recommends -y ca-certificates gnupg locales apt-transport-https dirmngr
locale-gen en_US.UTF-8

# Set up OONI archive
echo 'deb http://deb-ci.ooni.org unstable main' \
  > /etc/apt/sources.list.d/ooni.list
apt-key adv --keyserver hkp://keyserver.ubuntu.com \
  --recv-keys "B5A08F01796E7F521861B449372D1FF271F2DD50"

apt-get update
# Keep this in sync with debian/control
# hint: grep debdeps **/*.py
apt-get install --no-install-recommends -qy \
  curl \
  git \
  gunicorn3 \
  python3-boto3 \
  python3-clickhouse-driver \
  python3-filelock \
  python3-flasgger \
  python3-flask \
  python3-flask-cors \
  python3-flask-restful \
  python3-freezegun \
  python3-geoip2 \
  python3-git \
  python3-jwt \
  python3-lmdb \
  python3-lz4 \
  python3-mock \
  python3-psycopg2 \
  python3-pytest \
  python3-pytest-benchmark\
  python3-pytest-cov \
  python3-pytest-mock \
  python3-setuptools \
  python3-sqlalchemy \
  python3-sqlalchemy-utils \
  python3-statsd \
  python3-systemd \
  python3-ujson
apt-get autoremove -y
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

  #python3-lz4framed \

mkdir -p /etc/ooni/
cp api.conf.example /etc/ooni/api.conf
