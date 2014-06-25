# ooni backend
# ************
#
# This is the backend system responsible for running certain services that are
# useful for censorship detection.
#
# In here we start all the test helpers that are required by ooniprobe and
# start the report collector

from twisted.application import internet, service
from twisted.names import dns

from oonib.testhelpers import dns_helpers, ssl_helpers
from oonib.testhelpers import http_helpers, tcp_helpers

from oonib.config import config

if config.main.uid and config.main.gid:
    application = service.Application('oonibackend', uid=config.main.uid,
                                      gid=config.main.gid)
else:
    application = service.Application('oonibackend')

serviceCollection = service.IServiceCollection(application)

if config.helpers['ssl'].port:
    print "Starting SSL helper on %s" % config.helpers['ssl'].port
    ssl_helper = internet.SSLServer(int(config.helpers['ssl'].port),
                                    http_helpers.HTTPReturnJSONHeadersHelper(),
                                    ssl_helpers.SSLContext(config))
    ssl_helper.setServiceParent(serviceCollection)

# Start the DNS Server related services
if config.helpers['dns'].tcp_port:
    print "Starting TCP DNS Helper on %s" % config.helpers['dns'].tcp_port
    tcp_dns_helper = internet.TCPServer(int(config.helpers['dns'].tcp_port),
                                        dns_helpers.DNSTestHelper())
    tcp_dns_helper.setServiceParent(serviceCollection)

if config.helpers['dns'].udp_port:
    print "Starting UDP DNS Helper on %s" % config.helpers['dns'].udp_port
    udp_dns_factory = dns.DNSDatagramProtocol(dns_helpers.DNSTestHelper())
    udp_dns_helper = internet.UDPServer(int(config.helpers['dns'].udp_port),
                                        udp_dns_factory)
    udp_dns_helper.setServiceParent(serviceCollection)

if config.helpers['dns_discovery'].udp_port:
    print ("Starting UDP DNS Discovery Helper on %s" %
           config.helpers['dns_discovery'].udp_port)
    udp_dns_discovery = internet.UDPServer(int(config.helpers['dns_discovery'].udp_port),
                                           dns.DNSDatagramProtocol(
                                               dns_helpers.DNSResolverDiscovery()
                                           ))
    udp_dns_discovery.setServiceParent(serviceCollection)

if config.helpers['dns_discovery'].tcp_port:
    print ("Starting TCP DNS Discovery Helper on %s" %
           config.helpers['dns_discovery'].tcp_port)
    tcp_dns_discovery = internet.TCPServer(int(config.helpers['dns_discovery'].tcp_port),
                                           dns_helpers.DNSResolverDiscovery())
    tcp_dns_discovery.setServiceParent(serviceCollection)


# XXX this needs to be ported
# Start the OONI daphn3 backend
if config.helpers['daphn3'].port:
    print "Starting Daphn3 helper on %s" % config.helpers['daphn3'].port
    daphn3_helper = internet.TCPServer(int(config.helpers['daphn3'].port),
                                       tcp_helpers.Daphn3Server())
    daphn3_helper.setServiceParent(serviceCollection)


if config.helpers['tcp-echo'].port:
    print "Starting TCP echo helper on %s" % config.helpers['tcp-echo'].port
    tcp_echo_helper = internet.TCPServer(int(config.helpers['tcp-echo'].port),
                                         tcp_helpers.TCPEchoHelper())
    tcp_echo_helper.setServiceParent(serviceCollection)

if config.helpers['http-return-json-headers'].port:
    print "Starting HTTP return request helper on %s" % config.helpers['http-return-json-headers'].port
    http_return_request_helper = internet.TCPServer(
        int(config.helpers['http-return-json-headers'].port),
        http_helpers.HTTPReturnJSONHeadersHelper())
    http_return_request_helper.setServiceParent(serviceCollection)
