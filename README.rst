oonibackend: backend infrastructure for ooniprobe
=================================================

.. image:: https://travis-ci.org/ooni/backend-legacy.png?branch=master
    :target: https://travis-ci.org/ooni/backend-legacy

.. image:: https://coveralls.io/repos/TheTorProject/ooni-backend/badge.png?branch=master
    :target: https://coveralls.io/r/TheTorProject/ooni-backend

oonibackend is used by ooniprobe to discover the addresses of test helpers (via
the bouncer) to submit reports to (via the collector) and to perform some
measurements that require a backend system to talk to (via test helpers).

If you are interested in supporting the OONI project by running this backend
infrastructure follow this guide and then inform OONI developers of the address
of your collector and test helper by sending an email to
ooni-talk@lists.torproject.org.

Dependencies and Installation
=============================

Distro dependencies (Debian)
----------------------------

There are a few dependencies which we recommend you get from your
distribution's archives::

    sudo apt-get install build-essential python-dev python-setuptools openssl libsqlite3-dev libffi-dev git curl libdumbnet-dev

Tor
...

You will need a Tor binary on your system. For complete instructions, see
also::

    https://www.torproject.org/docs/tor-doc-unix.html.en
    https://www.torproject.org/docs/rpms.html.en

If you've already got Tor, or plan to compile it yourself from source, great!
You can skip this step. Otherwise, if you're installing Tor (or reinstalling),
you'll want to make sure to get our keyring package in Debian::

    echo "deb http://deb.torproject.org/torproject.org wheezy main" | \
        sudo tee -a /etc/apt/sources.list
    gpg --keyserver keys.gnupg.net --recv EE8CBC9E886DDD89
    gpg --export A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89 | sudo apt-key add -
    sudo apt-get update
    sudo apt-get install deb.torproject.org-keyring tor tor-geoipdb

Pip (>=7.0.0)
.............

We recommend using the Pip>=7.0.0 because it included several important
security and privacy related patches:

 * It forces the use of HTTPS for [PyPI](pypi.python.org).
 * and checks package hash sums before installation, with support for hashes
   more collision-resistant than MD5.
 * It does not fetch insecure metadata from external sourced by default.
 * It does not support an insecure index without explicit opt in.

The least painful way (that we know of) to install a newer Pip is to use Pip's
get-pip script::

    # Grab the get-pip installer to make sure we have pip>=1.3.0
    curl -O https://bootstrap.pypa.io/get-pip.py
    sudo python ./get-pip.py  ## pip (>=7.0.0) is recommended for security reasons
    # And make sure we're actually using the newer one:
    sudo update-alternatives --install /usr/bin/pip pip /usr/local/bin/pip 0

Virtualenv
..........

We recommend that you use a python virtualenv. The recommended commands for
setting up this up and installing are::

    sudo pip install --upgrade virtualenv virtualenvwrapper
    # Setup the virtualenv directory:
    export WORKON_HOME=~/.virtualenvs && mkdir -p $WORKON_HOME
    source /usr/local/bin/virtualenvwrapper.sh
    # Clone ooni-backend:
    git clone https://github.com/TheTorProject/ooni-backend.git && cd ooni-backend
    # Create the virtualenv for ooni-backend...
    mkvirtualenv -a $PWD --unzip-setuptools --setuptools --no-site-packages oonib
    # ...and install ooni-backend (sudo is not necessary since we're in a virtualenv):
    pip install -r requirements.txt
    # Note: it is important that you install the requirements before you run
    # the setup.py script. If you fail to do so they will be downloaded over
    # plaintext.
    python setup.py install

Running an OONI collector
=========================

Configure oonib
---------------

Copy the example config file to ``oonib.conf``::

    cp oonib.conf.example oonib.conf

Then edit your configuration to fit your needs. The fields you should probably
end up changing are ``report_dir`` (the public web server directory where you
would like ooni-probe clients to be able to submit reports to, for example, if
the clients should submit POSTs to https://abcdef0123456789.onion/report then
this would simply be ``'report'``) and ``tor_datadir`` (where you would
like the spawned Tor process to keep its data). If you compiled Tor yourself,
you'll likely want to specify it for the ``tor_binary`` option.

To configure the format of the log for the bouncer, collector and the HTTP based
test helpers you can specify the `log_format` option in the main section.

By default this is the logging policy adopted::

    [{protocol}] {status} {request_method} {request_uri}  127.0.0.1 {request_time}ms

The supported keys are ``protocol``, ``status``, ``request_method``, ``remote_ip``,
``request_uri``, ``request_time``.

Configure bouncer and collector endpoints
.........................................

The bouncer and collector are HTTP applications ("protocols" in twisted terminology) that can be configured to run on top of plain TCP, TLS, or onion service endpoints.
Here is an example of the relevant part of the configuration::

    bouncer_endpoints:
    - {type: tls, port: 10443, cert: "private/fullchain.pem", privkey: "private/privkey.pem"}
    - {type: tcp, port: 10080}
    - {type: onion, hsdir: "/some/private/bouncer"}

    collector_endpoints:
    - {type: tls, port: 11443, fullchain: "private/fullchain.pem", privkey: "private/privkey.pem"}
    - {type: onion, hsdir: "/some/private/collector"}

`scripts/gen-ssl-key-cert.sh` in this repo contains the openssl command to generate a self-signed certificate which you can use for the tls endpoint.
txtorcon will use the hostname/private_key from the configured hsdir to start an onion service, or generate a new key if hsdir is empty.


Bouncer configuration
.....................

The bouncer.yaml file contains the list of collectors and test-helpers that are
available to ooniprobe for receiving network measurement results.

In our deployment of oonibackend the bouncer.yaml file is generated
automatically every 24 hours via a cronjob that runs `update-bouncer.py`.
What this script does is it fetches the collector addresses and IP address of
mlab nodes and joins them with the base bouncer information stored in
`/data/bouncer/bouncer-base.yaml`.

To specify additional test helpers (for example when they change address or
when a new test helper comes out) you will need to edit
`/data/bouncer/bouncer-base.yaml`.::

    collector:
      httpo://ihiderha53f36lsd.onion:
          test-helper: {dns: '213.138.109.232:57004', ssl: 'https://213.138.109.232', tcp-echo: '213.138.109.232', traceroute: '213.138.109.232', web-connectivity: 'httpo://ckjj3ra6456muu7o.onion'}

You need to edit the content of the dictionary `test-helper`. The keys are the
names of the test helpers.
The value is the address of the test helper and this depends on the type of
test helper.

Here is a list of test helpers:

* dns (value: xxx.xxx.xxx.xxx)

* ssl (value: https://xxx.xxx.xxx.xxx)

* tcp-echo (xxx.xxx.xxx.xxx)

* traceroute (xxx.xxx.xxx.xxx)

* web-connectivity (httpo://xxxxxxxxx.onion)

Moreover it is possible to specify test-helper-alternate addresses that are
used to determine alternative names for a given test helper.

Currently only `web-connectivity` supports the test-helper-alternate field.

This can be specified like follows::

    collector:
      httpo://ihiderha53f36lsd.onion:
          test-helper: {dns: '213.138.109.232:57004', ssl: 'https://213.138.109.232', tcp-echo: '213.138.109.232', traceroute: '213.138.109.232', web-connectivity: 'httpo://ckjj3ra6456muu7o.onion'}
          test-helper-alternate:
            web-connectivity:
            - {address: 'httpo://ckjj3ra6456muu7o.onion', type: 'onion'}
            - {address: 'https://web-connectivity.ooni.io', type: 'https'}
            - {address: 'http://web-connectivity.ooni.io', type: 'http'}
            - {address: 'https://xxxxxxxxx.cloudfront.net', type: 'cloudfront', front: 'a0.awsstatic.com'}

Also collectors can have a set of alternate addresses. These can be
specified inside of the `collector-alternate` key under the collector
address like so::

     collector:
      httpo://thirteenchars123.onion:
        collector-alternate:
        - {address: 'https://a.collector.ooni.io', type: 'https'}
        - {address: 'http://a.collector.ooni.io', type: 'http'}
        - {address: 'https://xxxxxxxxx.cloudfront.net', type: 'cloudfront', front: 'a0.awsstatic.com'}


The currently supported types are 'https' and 'http'.

Generate self signed certs for OONIB
....................................
If you want to use the HTTPS test helper, you will need to create a
certificate::

    openssl genrsa -des3 -out private.key 4096
    openssl req -new -key private.key -out server.csr
    cp private.key private.key.org
    # Remove passphrase from key
    openssl rsa -in private.key.org -out private.key
    openssl x509 -req -days 365 -in server.csr -signkey private.key -out certificate.crt
    rm private.key.org
    rm server.csr

If you decide to put your certificate and key somewhere else, don't forget to
update oonib.conf options ```helpers.ssl.private_key``` and ```helpers.ssl.certificate``` !

Redirect low ports with iptables
................................

The following iptables commands will map connections on low ports to those
bound by oonib::

    # Map port 80 to config.helpers['http-return-json-headers'].port  (default: 57001)
    iptables -t nat -A PREROUTING -p tcp -m tcp --dport 80 -j REDIRECT --to-ports 57001
    # Map port 443 to config.helpers.ssl.port  (default: 57006)
    iptables -t nat -A PREROUTING -p tcp -m tcp --dport 443 -j REDIRECT --to-ports 57006
    # Map port 53 udp to config.helpers.dns.udp_port (default: 57004)
    iptables -t nat -A PREROUTING -p tcp -m udp --dport 53 -j REDIRECT --tor-ports
    # Map port 53 tcp to config.helpers.dns.tcp_port (default: 57005)
    iptables -t nat -A PREROUTING -p tcp -m tcp --dport 53 -j REDIRECT --tor-ports

(For Experts Only) Tor2webmode
..............................

**WARNING**: provides no anonymity! Use only if you know what you are doing!
Tor2webmode will improve the performance of the collector Hidden Service by
discarding server-side anonymity.

You will need to build Tor from source. At the time of writing, the latest
stable Tor is tor-0.2.3.25. You should use the most recent stable Tor.

Example::

    git clone https://git.torproject.org/tor.git
    git checkout tor-0.2.3.25
    git verify-tag -v tor-0.2.3.25

You should see::

    object 17c24b3118224d6536c41fa4e1493a831fb29f0a
    type commit
    tag tor-0.2.3.25
    tagger Roger Dingledine <arma@torproject.org> 1353399116 -0500

    tag 0.2.3.25
    gpg: Signature made Tue 20 Nov 2012 08:11:59 UTC
    gpg:                using RSA key C218525819F78451
    gpg: Good signature from "Roger Dingledine <arma@mit.edu>"
    gpg:                 aka "Roger Dingledine <arma@freehaven.net>"
    gpg:                 aka "Roger Dingledine <arma@torproject.org>"

It is always good idea to verify::

    $ gpg --recv-keys C218525819F78451
    [...]
    $ gpg --fingerprint C218525819F78451
    pub   4096R/C218525819F78451 2010-05-07
          Key fingerprint = F65C E37F 04BA 5B36 0AE6  EE17 C218 5258 19F7 8451
          uid               [  full  ] Roger Dingledine <arma@mit.edu>
          uid               [  full  ] Roger Dingledine <arma@freehaven.net>
          uid               [  full  ] Roger Dingledine <arma@torproject.org>
          sub   4096R/690234AC0DCC0FE1 2013-05-09 [expires: 2014-05-09]

Build Tor with enable-tor2web-mode::

    ./autogen.sh ; ./configure --enable-tor2web-mode ; make

Copy the tor binary from src/or/tor somewhere and set the corresponding
options in oonib.conf.

To launch oonib on system boot
------------------------------
To launch oonib on startup, you may want to use supervisord (www.supervisord.org)
The following supervisord config will use the virtual environment in
/home/ooni/venv_oonib and start oonib on boot::

    [program:oonib]
    command=/home/ooni/venv_oonib/bin/python /home/ooni/ooni-probe/bin/oonib
    autostart=true
    user=oonib
    directory=/home/oonib/

Testing with vagrant
--------------------

To test the deployment of oonib you may use [vagrant](http://www.vagrantup.com).

Once installed you will be able to install oonib in the virtual machine via::

    vagrant up
