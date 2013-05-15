#!/bin/bash

# 1. Fetch any dependencies
# we should have everything in the virtualenv? Or do we need to also get some
# system libraries? libyaml, anyone?
# XXX: Can we get a newer version of libyaml from a fc-xx repo?
#
# we'll need libyaml.h from the system's libraries, afaik. i don't know what
# the fc* repos have though. --isis
source /etc/mlab/slice-functions

# 2. Generate a ssl certificate
SCRIPT_ROOT=`pwd`
cd $SCRIPT_ROOT

#XXX: we should think about setting these fields more carefully
OPENSSL_SUBJECT="/C=US/ST=CA/CN="`hostname`
OPENSSL_PASS=file:$SCRIPT_ROOT/cert.pass
dd if=/dev/random of=$SCRIPT_ROOT/cert.pass bs=32 count=1
openssl genrsa -des3 -passout $OPENSSL_PASS -out private.key 4096
openssl req -new -passin $OPENSSL_PASS -key private.key -out server.csr -subj $OPENSSL_SUBJECT
cp private.key private.key.org

# Remove passphrase from key
openssl rsa -passin file:$SCRIPT_ROOT/cert.pass -in private.key.org -out private.key
chmod 600 private.key
openssl x509 -req -days 365 -in server.csr -signkey private.key -out certificate.crt
rm private.key.org
rm cert.pass

# get the UID and GID to drop privileges to
OONIB_UID=`id -u $SLICENAME`
OONIB_GID=`id -g $SLICENAME`

# randomly select either a tcp backend helper or a http backend helper to listen on port 80. Otherwise, bind to port 81
coin=$[$RANDOM % 2]
if [[ $coin > 0 ]]; then
  TCP_ECHO_PORT=80
  HTTP_ECHO_PORT=81
else
  TCP_ECHO_PORT=81
  HTTP_ECHO_PORT=80
fi

# drop a config in $SCRIPT_ROOT
echo "
main:
    report_dir: '/var/spool/$SLICENAME'
    tor_datadir: 
    database_uri: 'sqlite://"$SCRIPT_ROOT"/oonib_test_db.db'
    db_threadpool_size: 10
    tor_binary: '"$SCRIPT_ROOT"/bin/tor'
    tor2webmode: true
    pidfile: 'oonib.pid'
    nodaemon: false
    originalname: Null
    chroot: Null
    rundir: .
    umask: Null
    euid: Null
    uid: $OONIB_UID
    gid: $OONIB_GID
    uuid: Null
    no_save: true
    profile: Null
    debug: Null

helpers:
    http_return_request:
        port: $HTTP_ECHO_PORT
        server_version: Apache

    tcp_echo:
        port: $TCP_ECHO_PORT

    daphn3:
        yaml_file: Null
        pcap_file: Null
        port: 57003

    dns:
        udp_port: 57004
        tcp_port: 57005

    ssl:
        private_key: '"$SCRIPT_ROOT"/private.key'
        certificate: '"$SCRIPT_ROOT"/certificate.crt'
        port: 443" > $SCRIPT_ROOT/oonib.conf
