#!/bin/sh
# Note: ooniprobe currently does not support self-signed certificates hence this is to be used for testing purposes only.
set -eu

if [ ! -d private ]
then
  mkdir private
fi

openssl req -x509 -newkey rsa:2048 \
    -keyout private/ssl-key.pem -out private/ssl-cert.pem \
    -days 400 -nodes -subj '/CN=selfie'

cat private/ssl-key.pem private/ssl-cert.pem > private/ssl-key-and-cert.pem
