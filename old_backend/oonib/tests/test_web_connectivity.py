from hashlib import sha256
from twisted.internet import defer
from twisted.trial import unittest

from oonib.testhelpers.http_helpers import WebConnectivityCache

class WebConnectivityCacheTestCase(unittest.TestCase):
    def setUp(self):
        self.web_connectivity_cache = WebConnectivityCache()

    def tearDown(self):
        return self.web_connectivity_cache.expire_all()

    @defer.inlineCallbacks
    def test_http_request(self):
        value = yield self.web_connectivity_cache.http_request(
                    'https://www.google.com/humans.txt', {})
        self.assertEqual(
            value['body_length'], 286
        )
        self.assertEqual(
            value['status_code'], 200
        )
        self.assertIsInstance(value['headers'],
                              dict)

    @defer.inlineCallbacks
    def test_dns_consistency(self):
        # The twisted.names resolve set a reactor.callLater() on parsing the
        #  resolv.conf and this leads to the reactor being dirty. Look into
        # a clean way to solve this and reactive this integration test.
        self.skipTest("Skipping to avoid dirty reactor")
        value = yield self.web_connectivity_cache.dns_consistency(
                    'www.torproject.org')
        self.assertIsInstance(
            value['addrs'],
            list
        )
        self.assertIn(
            'failure',
            value.keys()
        )

    @defer.inlineCallbacks
    def test_tcp_connect(self):
        value = yield self.web_connectivity_cache.tcp_connect(
                    '216.58.213.14:80')
        self.assertIsInstance(
            value['status'],
            bool
        )
        self.assertIn(
            'failure',
            value.keys()
        )

    @defer.inlineCallbacks
    def test_cache_lifecycle(self):
        key = 'http://example.com'
        key_hash = sha256(key).hexdigest()
        value = {'spam': 'ham'}

        miss = yield self.web_connectivity_cache.lookup('http_request', key)
        self.assertEqual(miss, None)

        yield self.web_connectivity_cache.cache_value('http_request', key,
                                                      value)
        hit = yield self.web_connectivity_cache.lookup('http_request', key)
        self.assertEqual(hit, value)

        yield self.web_connectivity_cache.expire('http_request', key_hash)
