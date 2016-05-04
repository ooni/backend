#!/bin/sh
set -eu

if [ ! -d private ]
then
  mkdir private
fi

openssl req -x509 -newkey rsa:2048 \
    -keyout private/ssl-key.pem -out private/ssl-cert.pem \
    -days 400 -nodes -subj '/CN=selfie'

cat private/ssl-key.pem private/ssh-cert.pem > private/ssl-key-and-cert.pem
