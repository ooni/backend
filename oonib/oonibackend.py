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
from oonib.onion import startTor
from oonib.testhelpers import dns_helpers, ssl_helpers
from oonib.testhelpers import http_helpers, tcp_helpers

import os

from twisted.application import internet, service
from twisted.internet import reactor
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

# Start the DNS Server related services
if config.helpers['dns'].tcp_port:
    print "Starting TCP DNS Helper on %s" % config.helpers['dns'].tcp_port
    tcp_dns_helper = internet.TCPServer(int(config.helpers['dns'].tcp_port),
                                        dns_helpers.DNSTestHelper())
    multiService.addService(tcp_dns_helper)

if config.helpers['dns'].udp_port:
    print "Starting UDP DNS Helper on %s" % config.helpers['dns'].udp_port
    udp_dns_factory = dns.DNSDatagramProtocol(dns_helpers.DNSTestHelper())
    udp_dns_helper = internet.UDPServer(int(config.helpers['dns'].udp_port),
                                        udp_dns_factory)
    multiService.addService(udp_dns_helper)

if config.helpers['dns_discovery'].udp_port:
    print ("Starting UDP DNS Discovery Helper on %s" %
           config.helpers['dns_discovery'].udp_port)
    udp_dns_discovery = internet.UDPServer(int(config.helpers['dns_discovery'].udp_port),
                                           dns.DNSDatagramProtocol(
                                               dns_helpers.DNSResolverDiscovery()
                                           ))
    multiService.addService(udp_dns_discovery)

if config.helpers['dns_discovery'].tcp_port:
    print ("Starting TCP DNS Discovery Helper on %s" %
           config.helpers['dns_discovery'].tcp_port)
    tcp_dns_discovery = internet.TCPServer(int(config.helpers['dns_discovery'].tcp_port),
                                           dns_helpers.DNSResolverDiscovery())
    multiService.addService(tcp_dns_discovery)


# XXX this needs to be ported
# Start the OONI daphn3 backend
if config.helpers['daphn3'].port:
    print "Starting Daphn3 helper on %s" % config.helpers['daphn3'].port
    daphn3_helper = internet.TCPServer(int(config.helpers['daphn3'].port),
                                       tcp_helpers.Daphn3Server())
    multiService.addService(daphn3_helper)


if config.helpers['tcp-echo'].port:
    print "Starting TCP echo helper on %s" % config.helpers['tcp-echo'].port
    tcp_echo_helper = internet.TCPServer(int(config.helpers['tcp-echo'].port),
                                         tcp_helpers.TCPEchoHelper())
    multiService.addService(tcp_echo_helper)

if config.helpers['http-return-json-headers'].port:
    print "Starting HTTP return request helper on %s" % config.helpers['http-return-json-headers'].port
    http_return_request_helper = internet.TCPServer(
        int(config.helpers['http-return-json-headers'].port),
        http_helpers.HTTPReturnJSONHeadersHelper())
    multiService.addService(http_return_request_helper)


# add the tor collector service here
if config.main.tor_hidden_service:
    torconfig = TorConfig()
    d = startTor(torconfig)

    def getHSEndpoint(data_dir):
        if LooseVersion(txtorcon_version) >= LooseVersion('0.10.0'):
            return TCPHiddenServiceEndpoint(reactor,
                torconfig, 80, hidden_service_dir=data_dir)
        else:
            return TCPHiddenServiceEndpoint(reactor,
                torconfig, 80, data_dir=data_dir)

    def printOnionEndpoint(endpointService):
        print("Exposed %s Tor hidden service on httpo://%s" %
                (endpointService.name, endpointService.endpoint.onion_uri))

    def addCollector(torControlProtocol):
        data_dir = os.path.join(torconfig.DataDirectory, 'collector')
        collector_service = internet.StreamServerEndpointService(
                getHSEndpoint(data_dir),
                ooniBackend)
        collector_service.setName('collector')
        multiService.addService(collector_service)
        collector_service.startService()
        return collector_service

    d.addCallback(addCollector)
    d.addCallback(printOnionEndpoint)

    if ooniBouncer:
        def addBouncer(torControlProtocol):
            data_dir = os.path.join(torconfig.DataDirectory, 'bouncer')
            bouncer_service = internet.StreamServerEndpointService(
                    getHSEndpoint(data_dir),
                    ooniBouncer)
            bouncer_service.setName('bouncer')
            multiService.addService(bouncer_service)
            bouncer_service.startService()
            return bouncer_service

        d.addCallback(addBouncer)
        d.addCallback(printOnionEndpoint)
else:
    if ooniBouncer:
        bouncer_service = internet.TCPServer(8888, ooniBouncer, interface="127.0.0.1")
        multiService.addService(bouncer_service)
        bouncer_service.startService()
    collector_service = internet.TCPServer(8889, ooniBackend, interface="127.0.0.1")
    multiService.addService(collector_service)
    collector_service.startService()
