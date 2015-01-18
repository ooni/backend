from zope.interface import implementer, providedBy, directlyProvides
from twisted.protocols.policies import ProtocolWrapper
from twisted.internet.protocol import Protocol
from OpenSSL import SSL
from OpenSSL.SSL import WantReadError
from twisted.protocols.tls import TLSMemoryBIOProtocol
# from twisted.protocols.tls import TLSMemoryBIOFactory
# from twisted.internet import ssl
from twisted.internet.interfaces import IOpenSSLClientConnectionCreator
from twisted.internet.interfaces import IOpenSSLServerConnectionCreator
from oonib.config import config


cached_certs = {
    "127.0.0.1:8989": {
        "private_key_file": "somepath",
        "certificate_key_file": "somepath"
    },
    "default": {
        "private_key_file": config.helpers.ssl.private_key,
        "certificate_file": config.helpers.ssl.certificate
    }
}


@implementer(IOpenSSLClientConnectionCreator, IOpenSSLServerConnectionCreator)
class SmartConnectionCreatorFactory(object):
    """
    A provider of L{IOpenSSLServerConnectionCreator} can create
    L{OpenSSL.SSL.Connection} objects for TLS servers.

    @see: L{twisted.internet.ssl}

    @note: Creating OpenSSL connection objects is subtle, error-prone, and
        security-critical.  Before implementing this interface yourself,
        consider using L{twisted.internet.ssl.CertificateOptions} as your
        C{contextFactory}.  (For historical reasons, that class does not
        actually I{implement} this interface; nevertheless it is usable in all
        Twisted APIs which require a provider of this interface.)
    """

    def serverConnectionForTLS(self, tlsProtocol):
        """
        Create a connection for the given server protocol.

        @param tlsProtocol: the protocol server making the request.
        @type tlsProtocol: L{twisted.protocols.tls.TLSMemoryBIOProtocol}.

        @return: an OpenSSL connection object configured appropriately for the
            given Twisted protocol.
        @rtype: L{OpenSSL.SSL.Connection}
        """
        peer = tlsProtocol.transport.getPeer()

        key = "%s:%s" % (peer.host, peer.port)
        try:
            cert = cached_certs[key]
        except KeyError:
            print "Could not find cert for %s" % key
            cert = cached_certs['default']

        ctx = SSL.Context(SSL.SSLv23_METHOD)
        # Disallow SSLv2!  It's insecure!  SSLv3 has been around since
        # 1996.  It's time to move on.
        ctx.set_options(SSL.OP_NO_SSLv2)
        ctx.use_certificate_file(cert['certificate_file'])
        ctx.use_privatekey_file(cert['private_key_file'])

        return SSL.Connection(ctx, None)


def makeConnectionPatched(self, transport):
    """
    Connect this wrapper to the given transport and initialize the
    necessary L{OpenSSL.SSL.Connection} with a memory BIO.
    """
    self._appSendBuffer = []

    # Add interfaces provided by the transport we are wrapping:
    for interface in providedBy(transport):
        directlyProvides(self, interface)

    # Intentionally skip ProtocolWrapper.makeConnection - it might call
    # wrappedProtocol.makeConnection, which we want to make conditional.
    Protocol.makeConnection(self, transport)
    self.factory.registerProtocol(self)

    # The only change is moving the creation of the context factory to after
    # the transport has been initialized.
    self._tlsConnection = self.factory._createConnection(self)

    if self._connectWrapped:
        # Now that the TLS layer is initialized, notify the application of
        # the connection.
        ProtocolWrapper.makeConnection(self, transport)

    # Now that we ourselves have a transport (initialized by the
    # ProtocolWrapper.makeConnection call above), kick off the TLS
    # handshake.
    try:
        self._tlsConnection.do_handshake()
    except WantReadError:
        # This is the expected case - there's no data in the connection's
        # input buffer yet, so it won't be able to complete the whole
        # handshake now.  If this is the speak-first side of the
        # connection, then some bytes will be in the send buffer now; flush
        # them.
        self._flushSendBIO()
TLSMemoryBIOProtocol.makeConnection = makeConnectionPatched
