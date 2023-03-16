import json

from twisted.internet import defer

from cyclone import web

from oonib.tests.handler_helpers import HandlerTestCase
from oonib.main.api import mainAPI


class GlobalHandler(HandlerTestCase):
    app = web.Application(mainAPI, name='mainAPI')

    @defer.inlineCallbacks
    def test_global_handler(self):
        response = yield self.request("/foo")
        res = json.loads(response.body)
        self.assertIn("error", res.keys())
        self.assertIn(404, res.values())
