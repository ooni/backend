from twisted.internet.protocol import Factory, Protocol
from twisted.internet import reactor
from twisted.names import dns
from twisted.names import client, server

from oonib.config import config

class DNSTestHelper(server.DNSServerFactory):
    def __init__(self, authorities = None,
                 caches = None, clients = None,
                 verbose = 0):
        try:
            host, port = config.helpers.dns.split(':')
            port = int(port)
        # XXX remove this when we have configuration file versioning.
        # https://github.com/TheTorProject/ooni-probe/issues/190
        except:
            host, port = '8.8.8.8', 53
        resolver = client.Resolver(servers=[(host, port)])
        server.DNSServerFactory.__init__(self, authorities = authorities,
                                         caches = caches, clients = [resolver],
                                         verbose = verbose)
    def handleQuery(self, message, protocol, address):
        server.DNSServerFactory.handleQuery(self, message, protocol, address)
