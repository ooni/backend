#!/bin/sh

# 1. Fetch any dependencies
# we should have everything in the virtualenv? Or do we need to also get some
# system libraries? libyaml, anyone?
# XXX: Can we get a newer version of libyaml from a fc-xx repo?

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

# Set up our firewall rules
# XXX: Confirm that sudo will work with MLAB.
# Map port 80 to config.helpers.http_return_request.port  (default: 57001)
sudo iptables -t nat -A PREROUTING -p tcp -m tcp --dport 80 -j REDIRECT --to-ports 57001
# Map port 443 to config.helpers.ssl.port  (default: 57006)
sudo iptables -t nat -A PREROUTING -p tcp -m tcp --dport 443 -j REDIRECT --to-ports 57006
# Map port 53 udp to config.helpers.dns.udp_port (default: 57004)
sudo iptables -t nat -A PREROUTING -p udp -m udp --dport 53 -j REDIRECT --to-ports 57004
# Map port 53 tcp to config.helpers.dns.tcp_port (default: 57005)
sudo iptables -t nat -A PREROUTING -p tcp -m tcp --dport 53 -j REDIRECT --to-ports 57005

# drop a config in $SCRIPT_ROOT
echo "
main:
    report_dir: 
    tor_datadir: 
    database_uri: 'sqlite:"$SCRIPT_ROOT"//oonib_test_db.db'
    db_threadpool_size: 10
    tor_binary: '"$SCRIPT_ROOT"/bin/tor'
    tor2webmode: true
    pidfile: 'oonib.pid'
    nodaemon: true
    originalname: Null
    chroot: Null
    rundir: .
    umask: Null
    euid: Null
    uid: Null
    gid: Null
    uuid: Null
    no_save: true
    profile: Null
    debug: Null

helpers:
    http_return_request:
        port: 57001
        server_version: Apache

    tcp_echo:
        port: 57002

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
        port: 57006" > $SCRIPT_ROOT/oonib.conf
