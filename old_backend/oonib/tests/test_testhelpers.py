import json
from twisted.internet import defer

from oonib.tests.handler_helpers import HandlerTestCase
from oonib.testhelpers import http_helpers


class TestHTTPReturnJSONHeaders(HandlerTestCase):
    app = http_helpers.HTTPReturnJSONHeadersHelper()

    @defer.inlineCallbacks
    def test_get_request(self):
        response = yield self.request('/', "GET",
                                      headers={'X-Antani': ['Spam']})
        response_body = json.loads(response.body)
        self.assertIn("headers_dict", response_body)
        self.assertIn("X-Antani", response_body['headers_dict'])
        self.assertIn(["X-Antani", "Spam"], response_body['request_headers'])
        self.assertEqual("GET / HTTP/1.1", response_body['request_line'])


class TestHTTPRandomPage(HandlerTestCase):
    app = http_helpers.HTTPRandomPageHelper

    @defer.inlineCallbacks
    def test_get_request(self):
        response = yield self.request('/100/ham', "GET")
        self.assertEqual(len(response.body), 104)
