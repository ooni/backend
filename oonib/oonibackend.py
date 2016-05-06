# ooni backend
# ************
#
# This is the backend system responsible for running certain services that are
# useful for censorship detection.
#
# In here we start all the test helpers that are required by ooniprobe and
# start the report collector

from distutils.version import LooseVersion

from oonib.api import ooniBackend, ooniBouncer
from oonib.config import config
from oonib.onion import configTor
from oonib.testhelpers import dns_helpers, ssl_helpers
from oonib.testhelpers import http_helpers, tcp_helpers

import os

from twisted.application import internet, service
from twisted.internet import reactor, endpoints, defer, ssl, protocol
from twisted.names import dns

from txtorcon import TCPHiddenServiceEndpoint, TorConfig
from txtorcon import __version__ as txtorcon_version

if config.main.uid and config.main.gid:
    application = service.Application('oonibackend', uid=config.main.uid,
                                      gid=config.main.gid)
else:
    application = service.Application('oonibackend')

multiService = service.MultiService()

if config.helpers['ssl'].port:
    print "Starting SSL helper on %s" % config.helpers['ssl'].port
    ssl_helper = internet.SSLServer(int(config.helpers['ssl'].port),
                                    http_helpers.HTTPReturnJSONHeadersHelper(),
                                    ssl_helpers.SSLContext(config))
    multiService.addService(ssl_helper)
    ssl_helper.startService()

# Start the DNS Server related services
if config.helpers['dns'].tcp_port:
    print "Starting TCP DNS Helper on %s" % config.helpers['dns'].tcp_port
    tcp_dns_helper = internet.TCPServer(int(config.helpers['dns'].tcp_port),
                                        dns_helpers.DNSTestHelper())
    multiService.addService(tcp_dns_helper)
    tcp_dns_helper.startService()

if config.helpers['dns'].udp_port:
    print "Starting UDP DNS Helper on %s" % config.helpers['dns'].udp_port
    udp_dns_factory = dns.DNSDatagramProtocol(dns_helpers.DNSTestHelper())
    udp_dns_helper = internet.UDPServer(int(config.helpers['dns'].udp_port),
                                        udp_dns_factory)
    multiService.addService(udp_dns_helper)
    udp_dns_helper.startService()

if config.helpers['dns_discovery'].udp_port:
    print ("Starting UDP DNS Discovery Helper on %s" %
           config.helpers['dns_discovery'].udp_port)
    udp_dns_discovery = internet.UDPServer(
        int(config.helpers['dns_discovery'].udp_port),
        dns.DNSDatagramProtocol(dns_helpers.DNSResolverDiscovery())
    )
    multiService.addService(udp_dns_discovery)

if config.helpers['dns_discovery'].tcp_port:
    print ("Starting TCP DNS Discovery Helper on %s" %
           config.helpers['dns_discovery'].tcp_port)
    tcp_dns_discovery = internet.TCPServer(
        int(config.helpers['dns_discovery'].tcp_port),
        dns_helpers.DNSResolverDiscovery()
    )
    multiService.addService(tcp_dns_discovery)
    tcp_dns_discovery.startService()


# XXX this needs to be ported
# Start the OONI daphn3 backend
if config.helpers['daphn3'].port:
    print "Starting Daphn3 helper on %s" % config.helpers['daphn3'].port
    daphn3_helper = internet.TCPServer(int(config.helpers['daphn3'].port),
                                       tcp_helpers.Daphn3Server())
    multiService.addService(daphn3_helper)
    daphn3_helper.startService()


if config.helpers['tcp-echo'].port:
    print "Starting TCP echo helper on %s" % config.helpers['tcp-echo'].port
    tcp_echo_helper = internet.TCPServer(int(config.helpers['tcp-echo'].port),
                                         tcp_helpers.TCPEchoHelper())
    multiService.addService(tcp_echo_helper)
    tcp_echo_helper.startService()

if config.helpers['http-return-json-headers'].port:
    print ("Starting HTTP return request helper on %s" %
           config.helpers['http-return-json-headers'].port)
    http_return_request_helper = internet.TCPServer(
        int(config.helpers['http-return-json-headers'].port),
        http_helpers.HTTPReturnJSONHeadersHelper())
    multiService.addService(http_return_request_helper)
    http_return_request_helper.startService()

def getHSEndpoint(endpoint_config):
    hsdir = os.path.join(torconfig.DataDirectory, endpoint_config['hsdir'])
    if LooseVersion(txtorcon_version) >= LooseVersion('0.10.0'):
        return TCPHiddenServiceEndpoint.global_tor(reactor,
                                        80,
                                        hidden_service_dir=hsdir)
    else:
        return TCPHiddenServiceEndpoint.global_tor(reactor,
                                        80,
                                        data_dir=hsdir)

def getTCPEndpoint(endpoint_config):
    return endpoints.TCP4ServerEndpoint(reactor, endpoint_config['port'])

def getTLSEndpoint(endpoint_config):
    with open(endpoint_config['cert'], 'r') as f:
        cert_data = f.read()
    certificate = ssl.PrivateCertificate.loadPEM(cert_data)
    return endpoints.SSL4ServerEndpoint(reactor,
                                        endpoint_config['port'],
                                        certificate.options())

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
        factory = ooniBouncer
    elif role == 'collector':
        factory = ooniBackend
    else:
        raise Exception("unknown service type")

    service = internet.StreamServerEndpointService(
        endpoint, factory
    )
    service.setName("-".join([endpoint_config['type'], role]))
    multiService.addService(service)
    service.startService()

if config.main.tor_hidden_service:
    torconfig = TorConfig()
    configTor(torconfig)

# this is to ensure same behaviour with an old config file
if config.main.bouncer_endpoints is None:
    config.main.bouncer_endpoints = [ {'type': 'onion', 'hsdir': 'bouncer'} ]

if config.main.collector_endpoints is None:
    config.main.collector_endpoints = [ {'type': 'onion', 'hsdir': 'collector'} ]

for endpoint_config in config.main.bouncer_endpoints:
    print "Starting bouncer with config %s" % endpoint_config
    endpoint = getEndpoint(endpoint_config)
    createService(endpoint, 'bouncer', endpoint_config)

for endpoint_config in config.main.collector_endpoints:
    print "Starting collector with config %s" % endpoint_config
    endpoint = getEndpoint(endpoint_config)
    createService(endpoint, 'collector', endpoint_config)

