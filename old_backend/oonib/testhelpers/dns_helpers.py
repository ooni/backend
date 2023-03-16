from twisted.names import client, server, dns

from oonib.config import config


class DNSTestHelper(server.DNSServerFactory):
    def __init__(self, authorities=None,
                 caches=None, clients=None,
                 verbose=0):
        try:
            host, port = config.helpers.dns.split(':')
            port = int(port)
        # XXX remove this when we have configuration file versioning.
        # https://github.com/TheTorProject/ooni-probe/issues/190
        except:
            host, port = '8.8.8.8', 53
        resolver = client.Resolver(servers=[(host, port)])
        server.DNSServerFactory.__init__(self, authorities=authorities,
                                         caches=caches, clients=[resolver],
                                         verbose=verbose)

    def handleQuery(self, message, protocol, address):
        server.DNSServerFactory.handleQuery(self, message, protocol, address)


class DNSResolverDiscovery(server.DNSServerFactory):
    """
    This test helper is used to discover the IP address of the resolver being
    used by a ooniprobe client.
    To use it you should set it up on a machine that has been delegated as the
    authoritative name server for a specific subdomain.
    You can do so by adding the following to your zone file:

        mysubdomain                   IN    NS    ns.mysubdomain.example.org.
        ns.mysubdomain.example.org    IN    A     10.42.42.42

    Replace 10.42.42.42 with the IP address of the machine running oonib.

    You will then be able to perform A lookups on subdomains of
    mysubdomain.example.org and retrieve in the query answer section the IP
    address of the resolver that was used for performing the request.
    """
    def handleQuery(self, message, protocol, address):
        query = message.queries[0]
        if query.type == dns.A:
            ans = dns.RRHeader(bytes(query.name),
                               payload=dns.Record_A(bytes(address[0]), 0))
            message.answers = [ans]
            message.answer = 1
        self.sendReply(protocol, message, address)
