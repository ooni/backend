# ooni backend
# ************
#
# This is the backend system responsible for running certain services that are
# useful for censorship detection.
#
# In here we start all the test helpers that are required by ooniprobe and
# start the report collector

import os
import sys


from oonib.api import OONICollector, OONIBouncer
from oonib.config import config
from oonib.onion import get_global_tor
from oonib.testhelpers import dns_helpers, ssl_helpers
from oonib.testhelpers import http_helpers, tcp_helpers

from twisted.scripts import twistd
from twisted.python import usage
from twisted.application import internet, service
from twisted.internet import reactor, endpoints, ssl
from twisted.names import dns
from OpenSSL import SSL

class ChainedOpenSSLContext(ssl.DefaultOpenSSLContextFactory):
    def __init__(self, private_key_path, certificate_chain_path,
                 ssl_method=SSL.TLSv1_METHOD):
        self.private_key_path = private_key_path
        self.certificate_chain_path = certificate_chain_path
        self.ssl_method = ssl_method
        self.cacheContext()

    def cacheContext(self):
        ctx = SSL.Context(self.ssl_method)
        ctx.use_certificate_chain_file(self.certificate_chain_path)
        ctx.use_privatekey_file(self.private_key_path)
        self._context = ctx

def getHSEndpoint(endpoint_config):
    from txtorcon import TCPHiddenServiceEndpoint
    hsdir = endpoint_config['hsdir']
    hsdir = os.path.expanduser(hsdir)
    hsdir = os.path.realpath(hsdir)
    return TCPHiddenServiceEndpoint(reactor,
                                    config=get_global_tor(reactor),
                                    public_port=80,
                                    hidden_service_dir=hsdir)

def getTCPEndpoint(endpoint_config):
    return endpoints.TCP4ServerEndpoint(
                reactor=reactor,
                port=endpoint_config['port'],
                interface=endpoint_config.get('address', '')
    )

def getTLSEndpoint(endpoint_config):
    sslContextFactory = ChainedOpenSSLContext(
        endpoint_config['privkey'],
        endpoint_config['fullchain']
    )
    return endpoints.SSL4ServerEndpoint(
        reactor=reactor,
        port=endpoint_config['port'],
        sslContextFactory=sslContextFactory,
        interface=endpoint_config.get('address', '')
    )

def getEndpoint(endpoint_config):
    if endpoint_config['type'] == 'onion':
        return getHSEndpoint(endpoint_config)
    elif endpoint_config['type'] == 'tcp':
        return getTCPEndpoint(endpoint_config)
    elif endpoint_config['type'] == 'tls':
        return getTLSEndpoint(endpoint_config)
    else:
        raise Exception("unknown endpoint type")

def createService(endpoint, role, endpoint_config):
    if role == 'bouncer':
        factory = OONIBouncer()
    elif role == 'collector':
        factory = OONICollector()
    elif role == 'web_connectivity':
        factory = http_helpers.WebConnectivityHelper
    else:
        raise Exception("unknown service type")

    service = internet.StreamServerEndpointService(
        endpoint, factory
    )
    service.setName("-".join([endpoint_config['type'], role]))
    return service

class StartOONIBackendPlugin:
    tapname = "oonibackend"
    def makeService(self, so):
        ooniBackendService = service.MultiService()

        if config.helpers['ssl'].port:
            print "Starting SSL helper on %s" % config.helpers['ssl'].port
            ssl_helper = internet.SSLServer(int(config.helpers['ssl'].port),
                                            http_helpers.HTTPReturnJSONHeadersHelper(),
                                            ssl_helpers.SSLContext(config))
            ooniBackendService.addService(ssl_helper)

        # Start the DNS Server related services
        if config.helpers['dns'].tcp_port:
            print "Starting TCP DNS Helper on %s" % config.helpers['dns'].tcp_port
            tcp_dns_helper = internet.TCPServer(int(config.helpers['dns'].tcp_port),
                                                dns_helpers.DNSTestHelper())
            ooniBackendService.addService(tcp_dns_helper)

        if config.helpers['dns'].udp_port:
            print "Starting UDP DNS Helper on %s" % config.helpers['dns'].udp_port
            udp_dns_factory = dns.DNSDatagramProtocol(dns_helpers.DNSTestHelper())
            udp_dns_helper = internet.UDPServer(int(config.helpers['dns'].udp_port),
                                                udp_dns_factory)
            ooniBackendService.addService(udp_dns_helper)

        if config.helpers['dns_discovery'].udp_port:
            print ("Starting UDP DNS Discovery Helper on %s" %
                   config.helpers['dns_discovery'].udp_port)
            udp_dns_discovery = internet.UDPServer(
                int(config.helpers['dns_discovery'].udp_port),
                dns.DNSDatagramProtocol(dns_helpers.DNSResolverDiscovery())
            )
            ooniBackendService.addService(udp_dns_discovery)

        if config.helpers['dns_discovery'].tcp_port:
            print ("Starting TCP DNS Discovery Helper on %s" %
                   config.helpers['dns_discovery'].tcp_port)
            tcp_dns_discovery = internet.TCPServer(
                int(config.helpers['dns_discovery'].tcp_port),
                dns_helpers.DNSResolverDiscovery()
            )
            ooniBackendService.addService(tcp_dns_discovery)

        # XXX this needs to be ported
        # Start the OONI daphn3 backend
        if config.helpers['daphn3'].port:
            print "Starting Daphn3 helper on %s" % config.helpers['daphn3'].port
            daphn3_helper = internet.TCPServer(int(config.helpers['daphn3'].port),
                                               tcp_helpers.Daphn3Server())
            ooniBackendService.addService(daphn3_helper)

        if config.helpers['tcp-echo'].port:
            print "Starting TCP echo helper on %s" % config.helpers['tcp-echo'].port
            tcp_echo_helper = internet.TCPServer(int(config.helpers['tcp-echo'].port),
                                                 tcp_helpers.TCPEchoHelper())
            ooniBackendService.addService(tcp_echo_helper)

        if config.helpers['http-return-json-headers'].port:
            print ("Starting HTTP return request helper on %s" %
                   config.helpers['http-return-json-headers'].port)
            http_return_request_helper = internet.TCPServer(
                int(config.helpers['http-return-json-headers'].port),
                http_helpers.HTTPReturnJSONHeadersHelper())
            ooniBackendService.addService(http_return_request_helper)

        # this is to ensure same behaviour with an old config file
        if config.main.tor_hidden_service and \
                config.main.bouncer_endpoints is None and \
                config.main.collector_endpoints is None:
            bouncer_hsdir   = os.path.join(config.main.tor_datadir, 'bouncer')
            collector_hsdir = os.path.join(config.main.tor_datadir, 'collector')
            config.main.bouncer_endpoints   = [ {'type': 'onion', 'hsdir':   bouncer_hsdir} ]
            config.main.collector_endpoints = [ {'type': 'onion', 'hsdir': collector_hsdir} ]

        for endpoint_config in config.main.get('bouncer_endpoints', []):
            if config.main.bouncer_file:
                print "Starting bouncer with config %s" % endpoint_config
                endpoint = getEndpoint(endpoint_config)
                bouncer_service = createService(endpoint, 'bouncer',
                                                endpoint_config)
                ooniBackendService.addService(bouncer_service)
            else:
                print "No bouncer configured"

        for endpoint_config in config.main.get('collector_endpoints', []):
            print "Starting collector with config %s" % endpoint_config
            endpoint = getEndpoint(endpoint_config)
            collector_service = createService(endpoint, 'collector',
                                              endpoint_config)
            ooniBackendService.addService(collector_service)

        for endpoint_config in config.helpers.web_connectivity.get('endpoints', []):
            print "Starting web_connectivity helper with config %s" % endpoint_config
            endpoint = getEndpoint(endpoint_config)
            web_connectivity_service = createService(endpoint,
                                                     'web_connectivity',
                                                     endpoint_config)
            ooniBackendService.addService(web_connectivity_service)


        return ooniBackendService

class OONIBackendTwistdConfig(twistd.ServerOptions):
    subCommands = [("StartOONIBackend", None, usage.Options, "node")]

def start():
    twistd_args = []

    flags = [
        'nodaemon',
        'no_save'
    ]
    options = [
        'pidfile',
        'logfile',
        'rundir',
        'euid',
        'gid',
        'uid',
        'umask'
    ]
    for option in options:
        if config.main.get(option, None) is not None:
            twistd_args.append('--%s' % option)
            twistd_args.append(config.main.get(option))
    for flag in flags:
        if config.main.get(flag, None) is True:
            twistd_args.append('--%s'% flag)

    twistd_args.append('StartOONIBackend') # Point to our backend plugin
    twistd_config = OONIBackendTwistdConfig()
    try:
        twistd_config.parseOptions(twistd_args)
    except usage.error:
        print "Usage error from twistd"
        sys.exit(7)

    twistd_config.loadedPlugins = {'StartOONIBackend': StartOONIBackendPlugin()}
    twistd.runApp(twistd_config)
    return 0
