#!/bin/bash
# Called from Dockerfile
set -exu
export DEBIAN_FRONTEND=noninteractive

echo 'deb http://deb.debian.org/debian buster-backports main' > /etc/apt/sources.list.d/backports.list

apt-get update
apt-get install --no-install-recommends -y ca-certificates
echo 'deb [trusted=yes] https://dl.bintray.com/ooni/internal-pull-requests unstable main' \
  > /etc/apt/sources.list.d/ooni.list
apt-get update

apt-get install locales -y
locale-gen en_US.UTF-8
apt-get install git --no-install-recommends -y \
      gunicorn3 \
      python3-boto3 \
      python3-flasgger \
      python3-flask \
      python3-flask-cors \
      python3-flask-restful \
      python3-flask-security \
      python3-lz4 \
      python3-lz4framed \
      python3-psycopg2 \
      python3-pytest \
      python3-setuptools \
      python3-sqlalchemy \
      python3-sqlalchemy-utils \
      python3-statsd \
      python3-systemd \
      python3-ujson
apt-get autoremove -y
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

mkdir /etc/ooni/
