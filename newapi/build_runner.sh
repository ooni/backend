#!/bin/bash
# Called from spawnrunner
set -eu
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

mkdir -p /etc/ooni/
cat > /etc/ooni/api.conf <<EOF
# Configuration for OONI API
# Syntax: treat it as a Python file, but only uppercase variables are used
COLLECTORS = []

# Read-only database access
DATABASE_URI_RO = "postgresql://amsapi:b2HUU6gKM19SvXzXJCzpUV@localhost/metadb"

DATABASE_STATEMENT_TIMEOUT = 30
BASE_URL = "https://api.ooni.io/"

AUTOCLAVED_BASE_URL = "http://datacollector.infra.ooni.io/ooni-public/autoclaved/"

# S3 endpoint
S3_ACCESS_KEY_ID = "CHANGEME"
S3_SECRET_ACCESS_KEY = "CHANGEME"
S3_SESSION_TOKEN = "CHANGEME"
S3_ENDPOINT_URL = "CHANGEME"

# Registration email delivery
MAIL_SERVER = "CHANGEME"
MAIL_PORT = 465
MAIL_USE_SSL = True
MAIL_USERNAME = "CHANGEME"
MAIL_PASSWORD = "CHANGEME"

#SECRET_KEY = "CHANGEME"

# Measurement spool directory
MSMT_SPOOL_DIR = "/var/lib/ooniapi/measurements"
EOF

