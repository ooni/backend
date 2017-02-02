import json
import os
import random
import re
import string
import tempfile
from hashlib import sha256
from urlparse import urlparse

from cyclone.web import RequestHandler, Application, HTTPError
from cyclone.web import asynchronous
from twisted.internet import protocol, defer, reactor
from twisted.internet.endpoints import TCP4ClientEndpoint

from twisted.internet.error import ConnectionRefusedError, ConnectError
from twisted.internet.error import DNSLookupError, TimeoutError

from twisted.names import client as dns_client
from twisted.names import dns
from twisted.names.error import DNSNameError, DNSServerError
from twisted.protocols import policies, basic
from twisted.web.client import readBody
from twisted.web.client import ContentDecoderAgent, GzipDecoder
from twisted.web.client import PartialDownloadError
from twisted.web.http import Request

from oonib.api import log_function
from oonib import log, randomStr

from oonib.common.txextra import FixedRedirectAgent, TrueHeaders
from oonib.common.txextra import TrueHeadersAgent
from oonib.common.http_utils import representBody, extractTitle
from oonib.common.http_utils import REQUEST_HEADERS
from oonib.common.tcp_utils import TCPConnectFactory

from oonib.handlers import OONIBHandler


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
    if (hasattr(response, 'body') and
                response.body is not None):
        body = response.body
        body_length = len(response.body)
    headers = {}
    for k, v in response.headers.getAllRawHeaders():
        headers[k.lower()] = unicode(v[0], errors='ignore')
    return {
        'headers': headers,
        'code': response.code,
        'body_length': body_length,
        'body': representBody(body)
    }

def encodeResponses(response):
    responses = []
    responses += [encodeResponse(response)]
    if response.previousResponse:
        responses += encodeResponses(response.previousResponse)
    return responses


class WebConnectivityCache(object):
    expiration_time = 200
    enable_caching = True
    http_retries = 2

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
    def http_request(self, url, http_request_headers, include_http_responses=False):
        key = url + json.dumps(http_request_headers)
        cached_value = yield self.lookup('http_request', key)
        if cached_value is not None:
            if include_http_responses is not True:
                cached_value.pop('responses', None)
            defer.returnValue(cached_value)

        page_info = {
            'body_length': -1,
            'status_code': -1,
            'headers': {},
            'failure': None
        }

        agent = ContentDecoderAgent(
            FixedRedirectAgent(TrueHeadersAgent(reactor),
                               ignorePrivateRedirects=True),
            [('gzip', GzipDecoder)]
        )
        try:
            retries = 0
            while True:
                try:
                    response = yield agent.request('GET', url,
                                                   TrueHeaders(http_request_headers))
                    headers = {}
                    for name, value in response.headers.getAllRawHeaders():
                        headers[name] = unicode(value[0], errors='ignore')
                    body_length = -1
                    body = None
                    try:
                        body = yield readBody(response)
                        body_length = len(body)
                    except PartialDownloadError as pde:
                        if pde.response:
                            body_length = len(pde.response)
                            body = pde.response
                    page_info['body_length'] = body_length
                    page_info['status_code'] = response.code
                    page_info['headers'] = headers
                    page_info['title'] = extractTitle(body)
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
        except ConnectError:
            page_info['failure'] = 'connect_error'
        except Exception as exc:
            # XXX map more failures
            page_info['failure'] = 'unknown_error'
            log.err("Unknown error occurred")
            log.exception(exc)

        yield self.cache_value('http_request', key, page_info)
        if include_http_responses is not True:
            page_info.pop('responses', None)
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
        except ConnectError:
            socket_info['status'] = False
            socket_info['failure'] = 'connect_error'
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


# Taken from
# http://stackoverflow.com/questions/7160737/python-how-to-validate-a-url-in-python-malformed-or-not
HTTP_REQUEST_REGEXP = re.compile(
    r'^(?:http)s?://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE)

SOCKET_REGEXP = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$')

web_connectivity_cache = WebConnectivityCache()

class WebConnectivity(OONIBHandler):
    @defer.inlineCallbacks
    def control_measurement(self, http_url, socket_list,
                            include_http_responses,
                            invalid_sockets,
                            http_request_headers=None):
        if http_request_headers is None:
            http_request_headers = {}

        hostname = urlparse(http_url).netloc
        dl = [
            web_connectivity_cache.http_request(http_url, http_request_headers, include_http_responses),
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
        for invalid_socket in invalid_sockets:
            tcp_connect[invalid_socket] = {
                "status": None,
                "failure": "invalid_socket"
            }
        self.finish({
            'http_request': http_request,
            'tcp_connect': tcp_connect,
            'dns': dns
        })

    def validate_request(self, request):
        allowed_headers = ['user-agent', 'accept', 'accept-language']
        required_keys = ['http_request', 'tcp_connect']
        for rk in required_keys:
            if rk not in request.keys():
                raise HTTPError(400, "Missing %s" % rk)
        if not HTTP_REQUEST_REGEXP.match(request['http_request']):
            raise HTTPError(400, "Invalid http_request URL")

        http_request_headers = request.get('http_request_headers', {})
        for k, v in http_request_headers.iteritems():
            if k.lower() not in allowed_headers:
                raise HTTPError(400, "Invalid header %s" % k)
            if not isinstance(v, list):
                raise HTTPError(400, "Headers must be a list")
        # We don't need to check the tcp_connect field because we strip it in
        # the post already.

    @asynchronous
    def post(self):
        try:
            request = json.loads(self.request.body)

            # Here we fix inconsistencies in the tcp_connect field.  Due to:
            # https://github.com/TheTorProject/ooni-probe/issues/727 ooniprobe
            # was sending hostnames as part of the tcp_connect key as well as
            # IP addresses.
            # If we find something that isn't an IP address we return it with
            # the key value None to support backward compatibility with older
            # bugged clients.
            tcp_connect = []
            invalid_sockets = []
            for socket in request['tcp_connect']:
                if SOCKET_REGEXP.match(socket):
                    tcp_connect.append(socket)
                else:
                    invalid_sockets.append(socket)
            request['tcp_connect'] = tcp_connect

            self.validate_request(request)
            include_http_responses = request.get(
                    "include_http_responses",
                    False
            )

            # We convert headers to str so twisted is happy (unicode triggers
            # errors)
            http_request_headers = {}
            for k, v in request.get('http_request_headers', {}).iteritems():
                http_request_headers[str(k)] = map(str, v)
            self.control_measurement(
                http_url=str(request['http_request']),
                include_http_responses=include_http_responses,
                http_request_headers=http_request_headers,
                socket_list=request['tcp_connect'],
                invalid_sockets=invalid_sockets
            )
        except HTTPError:
            raise
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
], log_function=log_function)

WebConnectivityHelper = Application([
    (r"/status", WebConnectivityStatus),
    (r"/", WebConnectivity)
], log_function=log_function)
