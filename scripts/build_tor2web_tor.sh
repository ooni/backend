#!/bin/bash

# Versions of libraries that we need to build a static Tor
OPENSSL_VERSION=1.0.1e
LIBEVENT_VERSION=2.0.21-stable
ZLIB_VERSION=1.2.7
TOR_VERSION=0.2.3.25
ZLIB_MD5=60df6a37c56e7c1366cca812414f7b85

SCRIPT_ROOT=`pwd`

# Package URLS
URLS="\
https://www.torproject.org/dist/tor-$TOR_VERSION.tar.gz
https://www.torproject.org/dist/tor-$TOR_VERSION.tar.gz.asc
http://zlib.net/zlib-$ZLIB_VERSION.tar.gz
https://www.openssl.org/source/openssl-$OPENSSL_VERSION.tar.gz.asc
https://www.openssl.org/source/openssl-$OPENSSL_VERSION.tar.gz
https://github.com/downloads/libevent/libevent/libevent-$LIBEVENT_VERSION.tar.gz.asc
https://github.com/downloads/libevent/libevent/libevent-$LIBEVENT_VERSION.tar.gz"

# get key for nickm (libevent)
gpg --fingerprint 0xb35bf85bf19489d04e28c33c21194ebb165733ea
if [ $? -ne 0 ]; then 
  gpg --keyserver pgp.mit.edu --recv-keys 0xb35bf85bf19489d04e28c33c21194ebb165733ea
  gpg --fingerprint 0xb35bf85bf19489d04e28c33c21194ebb165733ea
  if [ $? -ne 0 ]; then exit ;fi
fi

# get key for Dr Stephen Henson (openssl)
gpg --fingerprint 0xd05d8c616e27e66041ecb1b8d57ee597
if [ $? -ne 0 ]; then 
  gpg --keyserver pgp.mit.edu --recv-keys 0xd05d8c616e27e66041ecb1b8d57ee597
  gpg --fingerprint 0xd05d8c616e27e66041ecb1b8d57ee597
  if [ $? -ne 0 ]; then exit ;fi
fi

# get key for arma (tor) tor
gpg --fingerprint 0xf65ce37f04ba5b360ae6ee17c218525819f78451
if [ $? -ne 0 ]; then 
  gpg --keyserver pgp.mit.edu --recv-keys 0xf65ce37f04ba5b360ae6ee17c218525819f78451
  gpg --fingerprint 0xf65ce37f04ba5b360ae6ee17c218525819f78451
  if [ $? -ne 0 ]; then exit ;fi
fi

for URL in $URLS; do
  wget -p -nc $URL
done

BUILD=$SCRIPT_ROOT/build
if [ ! -e $BUILD ]; then
  mkdir -p $BUILD
fi

# set up openssl
cd $SCRIPT_ROOT
gpg --verify openssl-$OPENSSL_VERSION.tar.gz.asc openssl-$OPENSSL_VERSION.tar.gz
if [ $? -ne 0 ]; then exit ;fi
tar xfz openssl-$OPENSSL_VERSION.tar.gz
cd openssl-$OPENSSL_VERSION
./config --prefix=$BUILD/openssl-$OPENSSL_VERSION no-shared no-dso && make && make install

# set up libevent
cd $SCRIPT_ROOT
gpg --verify libevent-$LIBEVENT_VERSION.tar.gz.asc libevent-$LIBEVENT_VERSION.tar.gz
if [ $? -ne 0 ]; then exit ;fi
tar xfz libevent-$LIBEVENT_VERSION.tar.gz
cd libevent-$LIBEVENT_VERSION
./configure --prefix=$BUILD/libevent-$LIBEVENT_VERSION -disable-shared --enable-static --with-pic && make && make install

# set up zlib
cd $SCRIPT_ROOT
echo "$ZLIB_MD5 zlib-$ZLIB_VERSION.tar.gz" | md5sum -c
if [ $? -ne 0 ]; then exit ;fi

tar xfz zlib-$ZLIB_VERSION.tar.gz
cd zlib-$ZLIB_VERSION
./configure --prefix=$BUILD/zlib-$ZLIB_VERSION --static && make && make install

# set up tor with tor2web mode
cd $SCRIPT_ROOT
gpg --verify tor-$TOR_VERSION.tar.gz.asc tor-$TOR_VERSION.tar.gz
tar xfz tor-$TOR_VERSION.tar.gz
cd tor-$TOR_VERSION
echo ./configure --enable-static-tor --with-libevent-dir=$BUILD/libevent-$LIBEVENT_VERSION --with-openssl-dir=$BUILD/openssl-$OPENSSL_VERSION --with-zlib-dir=$BUILD/zlib-$ZLIB_VERSION --enable-tor2web-mode && make
