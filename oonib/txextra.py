from twisted.web.http_headers import Headers
from twisted.web import error

from twisted.web.client import BrowserLikeRedirectAgent
from twisted.web._newclient import ResponseFailed
from twisted.web._newclient import HTTPClientParser, ParseError
from twisted.python.failure import Failure

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
