import json
import random
import string

from urlparse import urlparse

from twisted.internet.protocol import Factory, Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint

from twisted.internet.error import DNSLookupError, TimeoutError
from twisted.internet.error import ConnectionRefusedError
from twisted.internet import protocol, defer, reactor

from twisted.names.error import DNSNameError, DNSServerError
from twisted.names import client as dns_client
from twisted.names import dns

from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers

from cyclone.web import RequestHandler, Application, HTTPError
from cyclone.web import asynchronous

from twisted.protocols import policies, basic
from twisted.web.http import Request

from oonib import log, randomStr


class SimpleHTTPChannel(basic.LineReceiver, policies.TimeoutMixin):
    """
    This is a simplified version of twisted.web.http.HTTPChannel to overcome
    header lowercase normalization. It does not actually implement the HTTP
    protocol, but only the subset of it that we need for testing.

    What this HTTP channel currently does is process the HTTP Request Line and
    the Request Headers and returns them in a JSON datastructure in the order
    we received them.

    The returned JSON dict looks like so:

    {
        'request_headers':
            [['User-Agent', 'IE6'], ['Content-Length', 200]]
        'request_line':
            'GET / HTTP/1.1'
    }
    """
    requestFactory = Request
    __first_line = 1
    __header = ''
    __content = None

    length = 0
    maxHeaders = 500
    maxHeaderLineLength = 16384
    requestLine = ''

    timeOut = 60 * 60 * 12

    def __init__(self):
        self.headers = []
        self.requests = []

    def connectionMade(self):
        self.setTimeout(self.timeOut)

    def lineReceived(self, line):
        if (len(self.__header) + len(line)) >= self.maxHeaderLineLength \
                and not self.__first_line:
            log.err("Maximum header length reached.")
            return self.transport.loseConnection()

        if self.__first_line:
            self.requestLine = line
            self.__first_line = 0
        elif line == '':
            # We have reached the end of the headers.
            if self.__header:
                self.headerReceived(self.__header)
            self.__header = ''
            self.allHeadersReceived()
            self.setRawMode()
        elif line[0] in ' \t':
            # This is to support header field value folding over multiple lines
            # as specified by rfc2616.
            self.__header += '\n'+line
        else:
            if self.__header:
                self.headerReceived(self.__header)
            self.__header = line

    def headerReceived(self, line):
        try:
            header, data = line.split(':', 1)
            self.headers.append((header, data.strip()))
        except:
            log.err("Got malformed HTTP Header request field")
            log.err("%s" % line)

        if len(self.headers) >= self.maxHeaders:
            log.err("Maximum number of headers received.")
            self.closeConnection()

    def allHeadersReceived(self):
        headers_dict = {}
        for k, v in self.headers:
            if k not in headers_dict:
                headers_dict[k] = []
            headers_dict[k].append(v)

        response = {
            'request_headers': self.headers,
            'request_line': self.requestLine,
            'headers_dict': headers_dict
        }
        json_response = json.dumps(response)
        self.transport.write('HTTP/1.1 200 OK\r\n\r\n')
        self.transport.write('%s' % json_response)

        self.closeConnection()

    def closeConnection(self):
        if self._TimeoutMixin__timeoutCall and \
                not self._TimeoutMixin__timeoutCall.called:
            self._TimeoutMixin__timeoutCall.cancel()
            self._TimeoutMixin__timeoutCall = None
        self.transport.loseConnection()


class HTTPReturnJSONHeadersHelper(protocol.ServerFactory):
    protocol = SimpleHTTPChannel

    def buildProtocol(self, addr):
        return self.protocol()


class HTTPTrapAll(RequestHandler):
    def _execute(self, transforms, *args, **kwargs):
        self._transforms = transforms
        defer.maybeDeferred(self.prepare).addCallbacks(
            self._execute_handler,
            lambda f: self._handle_request_exception(f.value),
            callbackArgs=(args, kwargs))

    def _execute_handler(self, r, args, kwargs):
        if not self._finished:
            args = [self.decode_argument(arg) for arg in args]
            kwargs = dict((k, self.decode_argument(v, name=k))
                          for (k, v) in kwargs.iteritems())

            # This is where we do the patching
            # XXX this is somewhat hackish
            d = defer.maybeDeferred(self.all, *args, **kwargs)
            d.addCallbacks(self._execute_success, self._execute_failure)
            self.notifyFinish().addCallback(self.on_connection_close)


class HTTPRandomPage(HTTPTrapAll):
    """
    This generates a random page of arbitrary length and containing the string
    selected by the user.
    /<length>/<keyword>
    XXX this is currently disabled as it is not of use to any test.
    """
    isLeaf = True

    def _gen_random_string(self, length):
        return ''.join(random.choice(string.letters) for x in range(length))

    def genRandomPage(self, length=100, keyword=None):
        data = self._gen_random_string(length/2)
        if keyword:
            data += keyword
        data += self._gen_random_string(length - length/2)
        data += '\n'
        return data

    def all(self, length, keyword):
        self.set_header('Content-Disposition', 'attachment; filename="%s.txt"' % randomStr(10))
        length = 100
        if length > 100000:
            length = 100000
        self.write(self.genRandomPage(length, keyword))

class TCPConnectProtocol(Protocol):
    def connectionMade(self):
        self.transport.loseConnection()

class TCPConnectFactory(Factory):
    def buildProtocol(self, addr):
        return TCPConnectProtocol()

USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36'

class WebConnectivityCache(object):
    expiration_time = 200
    enable_caching = True

    def __init__(self):
        self._cache = {
            'http_request': {
            },
            'tcp_connect': {
            },
            'dns_consistency': {
            }
        }

    def cache_value(self, response_type, key, value):
        if self.enable_caching:
            self._cache[response_type][key] = {
                'value': value,
                'expiration': reactor.callLater(self.expiration_time,
                                                self.expire, response_type, key)
            }

    def expire(self, response_type, key):
        if self._cache[response_type][key]['expiration'].active():
            self._cache[response_type][key]['expiration'].cancel()
        del self._cache[response_type][key]

    def lookup(self, response_type, key):
        if not self.enable_caching:
            return None

        try:
            hit = self._cache[response_type][key]
            hit['expiration'].reset(self.expiration_time)
            return hit['value']
        except KeyError:
            return None

    def http_request(self, url):
        cached_value = self.lookup('http_request', url)
        if cached_value is not None:
            return defer.succeed(cached_value)

        result = defer.Deferred()
        agent = Agent(reactor)
        d = agent.request('GET', url, Headers({'User-Agent': [USER_AGENT]}))

        @d.addCallback
        @defer.inlineCallbacks
        def cb(response):
            headers = {}
            for name, value in response.headers.getAllRawHeaders():
                headers[name] = value[0]
            body = yield readBody(response)
            value = {
                'body_length': len(body),
                'headers': headers,
                'failure': None
            }
            self.cache_value('http_request', url, value)
            result.callback(value)

        @d.addErrback
        def eb(failure):
            if failure.check(DNSLookupError):
                failure_string = 'dns_lookup_error'
            elif failure.check(TimeoutError):
                failure_string = 'generic_timeout_error'
            elif failure.check(ConnectionRefusedError):
                failure_string = 'connection_refused_error'
            else:
                failure_string = 'unknown_error'
            value = {
                'body_length': None,
                'headers': {},
                'failure': failure_string
            }
            self.cache_value('http_request', url, value)
            result.callback(value)

        return result

    def tcp_connect(self, socket):
        cached_value = self.lookup('tcp_connect', socket)
        if cached_value is not None:
            return defer.succeed(cached_value)

        result = defer.Deferred()

        ip_address, port = socket.split(":")
        point = TCP4ClientEndpoint(reactor, ip_address, int(port))
        d = point.connect(TCPConnectFactory())
        @d.addCallback
        def cb(p):
            value = {
                'status': True,
                'failure': None
            }
            self.cache_value('tcp_connect', socket, value)
            result.callback(value)

        @d.addErrback
        def eb(failure):
            if failure.check(TimeoutError):
                failure_string = 'generic_timeout_error'
            elif failure.check(ConnectionRefusedError):
                failure_string = 'connection_refused_error'
            else:
                failure_string = 'unknown_error'
            value = {
                'status': False,
                'failure': failure_string
            }
            self.cache_value('tcp_connect', socket, value)
            result.callback(value)

        return result

    def dns_consistency(self, hostname):
        cached_value = self.lookup('dns_consistency', hostname)
        if cached_value is not None:
            return defer.succeed(cached_value)

        result = defer.Deferred()
        d = dns_client.lookupAddress(hostname)

        @d.addCallback
        def cb(records):
            ip_addresses = []
            answers = records[0]
            for answer in answers:
                if answer.type is dns.A:
                    ip_addresses.append(answer.payload.dottedQuad())
            value = {
                'ips': ip_addresses,
                'failure': None
            }
            self.cache_value('dns_consistency', hostname, value)
            result.callback(value)

        @d.addErrback
        def eb(failure):
            if failure.check(DNSNameError):
                failure_string = 'dns_name_error'
            elif failure.check(DNSServerError):
                failure_string = 'dns_server_failure'
            else:
                failure_string = 'unknown_error'
            value = {
                'ips': [],
                'failure': failure_string
            }
            self.cache_value('dns_consistency', hostname, value)
            result.callback(value)

        return result

web_connectivity_cache = WebConnectivityCache()

class WebConnectivity(RequestHandler):
    @defer.inlineCallbacks
    def control_measurement(self, http_url, socket_list):
        hostname = urlparse(http_url).netloc
        dl = [
            web_connectivity_cache.http_request(http_url),
            web_connectivity_cache.dns_consistency(hostname)
        ]
        for socket in socket_list:
            dl.append(web_connectivity_cache.tcp_connect(socket))
        responses = yield defer.DeferredList(dl)
        http_request = responses[0][1]
        dns = responses[1][1]
        tcp_connect = {}
        for idx, response in enumerate(responses[2:]):
            tcp_connect[socket_list[idx]] = response[1]
        self.finish({
            'http_request': http_request,
            'tcp_connect': tcp_connect,
            'dns': dns
        })

    @asynchronous
    def post(self):
        try:
            request = json.loads(self.request.body)
            self.control_measurement(
                str(request['http_request']),
                request['tcp_connect']
            )
        except Exception as exc:
            log.msg("Got invalid request")
            log.exception(exc)
            raise HTTPError(400, 'invalid request')

HTTPRandomPageHelper = Application([
    # XXX add regexps here
    (r"/(.*)/(.*)", HTTPRandomPage)
])

WebConnectivityHelper = Application([
    (r"/", WebConnectivity)
])
