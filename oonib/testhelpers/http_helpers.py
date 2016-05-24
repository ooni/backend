import os
import re
import json
import random
import string
import tempfile
from hashlib import sha256

from urlparse import urlparse

from twisted.python.failure import Failure

from twisted.internet.protocol import Factory, Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint

from twisted.internet.error import DNSLookupError, TimeoutError
from twisted.internet.error import ConnectionRefusedError
from twisted.internet import protocol, defer, reactor

from twisted.names.error import DNSNameError, DNSServerError
from twisted.names import client as dns_client
from twisted.names import dns

from twisted.web._newclient import HTTPClientParser, ParseError
from twisted.web.client import Agent, BrowserLikeRedirectAgent, readBody
from twisted.web.client import ContentDecoderAgent, GzipDecoder
from twisted.web.client import PartialDownloadError
from twisted.web.http_headers import Headers
from twisted.web import error

from twisted.web._newclient import ResponseFailed

from cyclone.web import RequestHandler, Application, HTTPError
from cyclone.web import asynchronous

from twisted.protocols import policies, basic
from twisted.web.http import Request

from oonib import log, randomStr

# Monkey patch to overcome issue in parsing of HTTP responses that don't
# contain 3 parts in the HTTP response line
old_status_received = HTTPClientParser.statusReceived
def statusReceivedPatched(self, status):
    try:
        return old_status_received(self, status)
    except ParseError as exc:
        if exc.args[0] == 'wrong number of parts':
            return old_status_received(self, status + " XXX")
        raise
HTTPClientParser.statusReceived = statusReceivedPatched

class FixedRedirectAgent(BrowserLikeRedirectAgent):
    """
    This is a redirect agent with this patch manually applied:
    https://twistedmatrix.com/trac/ticket/8265
    """
    def _handleRedirect(self, response, method, uri, headers, redirectCount):
        """
        Handle a redirect response, checking the number of redirects already
        followed, and extracting the location header fields.

        This is patched to fix a bug in infinite redirect loop.
        """
        if redirectCount >= self._redirectLimit:
            err = error.InfiniteRedirection(
                response.code,
                b'Infinite redirection detected',
                location=uri)
            raise ResponseFailed([Failure(err)], response)
        locationHeaders = response.headers.getRawHeaders(b'location', [])
        if not locationHeaders:
            err = error.RedirectWithNoLocation(
                response.code, b'No location header field', uri)
            raise ResponseFailed([Failure(err)], response)
        location = self._resolveLocation(response.request.absoluteURI, locationHeaders[0])
        deferred = self._agent.request(method, location, headers)

        def _chainResponse(newResponse):
            newResponse.setPreviousResponse(response)
            return newResponse

        deferred.addCallback(_chainResponse)
        # This is the fix to properly handle redirects
        return deferred.addCallback(
            self._handleResponse, method, uri, headers, redirectCount + 1)

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


def encodeResponse(response):
    body = None
    body_length = 0
    if getattr(response, 'body', None):
        body = response.body
        body_length = len(response.body)
    return {
        'headers':
            {k.lower(): v for k, v in response.headers.getAllRawHeaders()},
        'code': response.code,
        'body_length': body_length,
        'body': body
    }


def encodeResponses(response):
    responses = []
    responses += [encodeResponse(response)]
    if response.previousResponse:
        responses += encodeResponses(response.previousResponse)
    return responses


TITLE_REGEXP = re.compile("<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)

def extractTitle(body):
    m = TITLE_REGEXP.search(body, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    return ''


class TCPConnectProtocol(Protocol):
    def connectionMade(self):
        self.transport.loseConnection()

class TCPConnectFactory(Factory):
    def buildProtocol(self, addr):
        return TCPConnectProtocol()

REQUEST_HEADERS = {
    'User-Agent': ['Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, '
                   'like Gecko) Chrome/47.0.2526.106 Safari/537.36'],
    'Accept-Language': ['en-US;q=0.8,en;q=0.5'],
    'Accept': ['text/html,application/xhtml+xml,application/xml;q=0.9,'
               '*/*;q=0.8']
}

class TrueHeaders(Headers):
    def __init__(self, rawHeaders=None):
        self._rawHeaders = dict()
        if rawHeaders is not None:
            for name, values in rawHeaders.iteritems():
                if type(values) is list:
                    self.setRawHeaders(name, values[:])
                elif type(values) is dict:
                    self._rawHeaders[name.lower()] = values
                elif type(values) is str:
                    self.setRawHeaders(name, values)

    def setRawHeaders(self, name, values):
        if name.lower() not in self._rawHeaders:
            self._rawHeaders[name.lower()] = dict()
        self._rawHeaders[name.lower()]['name'] = name
        self._rawHeaders[name.lower()]['values'] = values

    def getAllRawHeaders(self):
        for k, v in self._rawHeaders.iteritems():
            yield v['name'], v['values']

    def getRawHeaders(self, name, default=None):
        if name.lower() in self._rawHeaders:
            return self._rawHeaders[name.lower()]['values']
        return default

class WebConnectivityCache(object):
    expiration_time = 200
    enable_caching = True
    http_retries = 2
    enable_debug = False

    def __init__(self):
        self._response_types = (
            'http_request',
            'tcp_connect',
            'dns_consistency'
        )
        self._cache_lifecycle = {}
        self._cache_dir = tempfile.mkdtemp()
        for response_type in self._response_types:
            os.mkdir(os.path.join(self._cache_dir, response_type))
            self._cache_lifecycle[response_type] = {}

    @defer.inlineCallbacks
    def expire_all(self):
        for response_type in self._cache_lifecycle.keys():
            for key_hash in self._cache_lifecycle[response_type].keys():
                yield self.expire(response_type, key_hash)

    @defer.inlineCallbacks
    def cache_value(self, response_type, key, value):
        if response_type not in self._response_types:
            raise Exception("Invalid response type")
        if self.enable_caching:
            key_hash = sha256(key).hexdigest()
            cache_file = os.path.join(self._cache_dir, response_type, key_hash)

            if key_hash in self._cache_lifecycle[response_type]:
                yield self.expire(response_type, key_hash)

            self._cache_lifecycle[response_type][key_hash] = {
                'expiration': reactor.callLater(self.expiration_time,
                                                self.expire,
                                                response_type, key_hash),
                'lock': defer.DeferredLock()
            }
            lock = self._cache_lifecycle[response_type][key_hash]['lock']
            yield lock.acquire()
            with open(cache_file, 'w+') as fw:
                json.dump(value, fw)
            lock.release()

    @defer.inlineCallbacks
    def expire(self, response_type, key_hash):
        if response_type not in self._response_types:
            raise Exception("Invalid response type")
        lifecycle = self._cache_lifecycle[response_type][key_hash]
        if lifecycle['expiration'].active():
            lifecycle['expiration'].cancel()

        yield lifecycle['lock'].acquire()
        try:
            os.remove(os.path.join(self._cache_dir, response_type, key_hash))
        except OSError:
            pass
        lifecycle['lock'].release()
        del self._cache_lifecycle[response_type][key_hash]

    @defer.inlineCallbacks
    def lookup(self, response_type, key):
        if not self.enable_caching:
            defer.returnValue(None)

        key_hash = sha256(key).hexdigest()
        cache_file = os.path.join(self._cache_dir, response_type, key_hash)

        if key_hash not in self._cache_lifecycle[response_type]:
            defer.returnValue(None)

        lock = self._cache_lifecycle[response_type][key_hash]['lock']
        expiration = \
            self._cache_lifecycle[response_type][key_hash]['expiration']

        yield lock.acquire()

        if not os.path.exists(cache_file):
            lock.release()
            defer.returnValue(None)

        with open(cache_file, 'r') as fh:
            value = json.load(fh)

        expiration.reset(self.expiration_time)
        lock.release()
        defer.returnValue(value)

    @defer.inlineCallbacks
    def http_request(self, url):
        cached_value = yield self.lookup('http_request', url)
        if cached_value is not None:
            defer.returnValue(cached_value)

        page_info = {
            'body_length': -1,
            'status_code': -1,
            'headers': {},
            'failure': None
        }

        agent = ContentDecoderAgent(FixedRedirectAgent(Agent(reactor)),
                                    [('gzip', GzipDecoder)])
        try:
            retries = 0
            while True:
                try:
                    response = yield agent.request('GET', url,
                                                   TrueHeaders(REQUEST_HEADERS))
                    headers = {}
                    for name, value in response.headers.getAllRawHeaders():
                        headers[name] = value[0]
                    body_length = -1
                    try:
                        body = yield readBody(response)
                        body_length = len(body)
                    except PartialDownloadError as pde:
                        if pde.response:
                            body_length = len(pde.response)
                    page_info['body_length'] = body_length
                    page_info['status_code'] = response.code
                    page_info['headers'] = headers
                    page_info['title'] = extractTitle(body)
                    if self.enable_debug:
                        response.body = body
                        page_info['responses'] = encodeResponses(response)
                    break
                except:
                    if retries > self.http_retries:
                        raise
                    retries += 1
        except DNSLookupError:
            page_info['failure'] = 'dns_lookup_error'
        except TimeoutError:
            page_info['failure'] = 'generic_timeout_error'
        except ConnectionRefusedError:
            page_info['failure'] = 'connection_refused_error'
        except:
            # XXX map more failures
            page_info['failure'] = 'unknown_error'

        yield self.cache_value('http_request', url, page_info)
        defer.returnValue(page_info)

    @defer.inlineCallbacks
    def tcp_connect(self, socket):
        cached_value = yield self.lookup('tcp_connect', socket)
        if cached_value is not None:
            defer.returnValue(cached_value)

        socket_info = {
            'status': None,
            'failure': None
        }

        ip_address, port = socket.split(":")
        try:
            point = TCP4ClientEndpoint(reactor, ip_address, int(port))
            yield point.connect(TCPConnectFactory())
            socket_info['status'] = True
        except TimeoutError:
            socket_info['status'] = False
            socket_info['failure'] = 'generic_timeout_error'
        except ConnectionRefusedError:
            socket_info['status'] = False
            socket_info['failure'] = 'connection_refused_error'
        except:
            socket_info['status'] = False
            socket_info['failure'] = 'unknown_error'
        yield self.cache_value('tcp_connect', socket, socket_info)
        defer.returnValue(socket_info)

    @defer.inlineCallbacks
    def dns_consistency(self, hostname):
        cached_value = yield self.lookup('dns_consistency', hostname)
        if cached_value is not None:
            defer.returnValue(cached_value)

        dns_info = {
            'addrs': [],
            'failure': None
        }

        try:
            records = yield dns_client.lookupAddress(hostname)
            answers = records[0]
            for answer in answers:
                if answer.type is dns.A:
                    dns_info['addrs'].append(answer.payload.dottedQuad())
                elif answer.type is dns.CNAME:
                    dns_info['addrs'].append(answer.payload.name.name)
        except DNSNameError:
            dns_info['failure'] = 'dns_name_error'
        except DNSServerError:
            dns_info['failure'] = 'dns_server_failure'
        except:
            dns_info['failure'] = 'unknown_error'

        yield self.cache_value('dns_consistency', hostname, dns_info)
        defer.returnValue(dns_info)


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


class WebConnectivityStatus(RequestHandler):
    def get(self):
        self.write({"status": "ok"})


HTTPRandomPageHelper = Application([
    # XXX add regexps here
    (r"/(.*)/(.*)", HTTPRandomPage)
])

WebConnectivityHelper = Application([
    (r"/status", WebConnectivityStatus),
    (r"/", WebConnectivity)
])
