# -*- encoding: utf8 -*-
import json

from twisted.internet import defer

from cyclone import web

from oonib.bouncer.api import bouncerAPI
from oonib.test.handler_helpers import HandlerTestCase

fake_bouncer_file = """
collector:
  fake_address:
    policy:
      input:
      - {id: fake_id}
      nettest:
      - {name: fake_nettest, version: 1.0}
      - {name: another_fake_nettest, version: 2.0}
    test-helper: {fake_test_helper: 'fake_hostname'}
"""

fake_default_collector = """
collector:
  fake_address:
    policy:
      input:
      - {id: fake_id}
      nettest:
      - {name: fake_nettest, version: 1.0}
      - {name: another_fake_nettest, version: 2.0}
    test-helper: {fake_test_helper: 'fake_hostname'}
  default_collector:
    test-helper: {fake_test_helper: 'fake_hostname'}
"""

fake_bouncer_file_multiple_collectors = """
collector:
  fake_addressA:
    policy:
      input:
      - {id: fake_id}
      nettest:
      - {name: fake_nettest, version: 1.0}
      - {name: another_fake_nettest, version: 2.0}
    test-helper: {fake_test_helper: 'fake_hostname'}

  fake_addressB:
    policy:
      input:
      - {id: fake_id}
      nettest:
      - {name: fake_nettest, version: 1.0}
      - {name: another_fake_nettest, version: 2.0}
    test-helper: {fake_test_helper: 'fake_hostname'}
"""

fake_for_test_helper_request = """
collector:
  fake_addressA:
    policy:
      input:
      - {id: fake_id}
      nettest:
      - {name: fake_nettest, version: 1.0}
    test-helper: {fake_test_helper: 'fake_hostname', exotic_test_helper: 'fake_hostname'}

  fake_addressB:
    test-helper: {fake_test_helper: 'fake_hostname'}
"""

reports_dir = 'data/reports'
archive_dir = 'data/archive'
input_dir = 'data/inputs'
decks_dir = 'data/decks'
bouncer_filename = 'fake_bouncer_file.yaml'
fake_config_file = """
main:
    report_dir: %s
    archive_dir: %s
    input_dir: %s
    deck_dir: %s
    bouncer_file: %s

helpers:
    fake_test_helper:
         attribute: value
""" % (reports_dir, archive_dir, input_dir, decks_dir, bouncer_filename)


class BaseTestBouncer(HandlerTestCase):
    def setUp(self, *args, **kw):
        self.make_dir(reports_dir)
        self.make_dir(archive_dir)
        self.make_dir(input_dir)
        self.make_dir(decks_dir)

        self.config_filename = 'fake_config.conf'
        with open(self.config_filename, 'w') as config_file:
            config_file.write(fake_config_file)

        super(BaseTestBouncer, self).setUp()
        self.filenames.add(bouncer_filename)
        self.filenames.add(self.config_filename)


class TestBouncer(BaseTestBouncer):
    app = web.Application(bouncerAPI, name='bouncerAPI')

    def setUp(self, *args, **kw):
        with open(bouncer_filename, 'w') as bouncer_file:
            bouncer_file.write(fake_bouncer_file)
        super(TestBouncer, self).setUp()

    @defer.inlineCallbacks
    def test_void_net_tests(self):
        data = {
            'net-tests': [
                {
                    "test-helpers": ['fake_test_helper'],
                    "input-hashes": [],
                    "name": '',
                    "version": '',
                },
            ]
        }

        response = yield self.request('/bouncer/net-tests', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('error', response_body)
        self.assertEqual('collector-not-found', response_body['error'])

    @defer.inlineCallbacks
    def test_net_tests(self):
        data = {
            'net-tests': [
                {
                    "test-helpers": [],
                    "input-hashes": [],
                    "name": 'fake_nettest',
                    "version": '1.0',
                },
            ]
        }

        response = yield self.request('/bouncer/net-tests', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('net-tests', response_body)
        self.assertEqual(len(response_body['net-tests']), 1)
        self.assertIn('name', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['name'], 'fake_nettest')
        self.assertIn('version', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['version'], '1.0')
        self.assertIn('input-hashes', response_body['net-tests'][0])
        self.assertEqual(len(response_body['net-tests'][0]['input-hashes']), 0)
        self.assertIn('test-helpers', response_body['net-tests'][0])
        self.assertEqual(len(response_body['net-tests'][0]['test-helpers']), 0)
        self.assertIn('collector', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['collector'], 'fake_address')

    @defer.inlineCallbacks
    def test_backward_compatibility(self):
        data = {
            'net-tests': [
                {
                    "test-helpers": [],
                    "input-hashes": [],
                    "name": 'fake_nettest',
                    "version": '1.0',
                },
            ]
        }

        response = yield self.request('/bouncer', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('net-tests', response_body)
        self.assertEqual(len(response_body['net-tests']), 1)
        self.assertIn('name', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['name'], 'fake_nettest')
        self.assertIn('version', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['version'], '1.0')
        self.assertIn('input-hashes', response_body['net-tests'][0])
        self.assertEqual(len(response_body['net-tests'][0]['input-hashes']), 0)
        self.assertIn('test-helpers', response_body['net-tests'][0])
        self.assertEqual(len(response_body['net-tests'][0]['test-helpers']), 0)
        self.assertIn('collector', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['collector'], 'fake_address')

    @defer.inlineCallbacks
    def test_multiple_net_tests(self):
        data = {
            'net-tests': [
                {
                    "test-helpers": [],
                    "input-hashes": [],
                    "name": 'fake_nettest',
                    "version": '1.0',
                },
                {
                    "test-helpers": [],
                    "input-hashes": [],
                    "name": 'another_fake_nettest',
                    "version": '1.0',
                }
            ]
        }

        response = yield self.request('/bouncer/net-tests', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('net-tests', response_body)
        self.assertEqual(len(response_body['net-tests']), 2)
        self.assertIn('name', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['name'], 'fake_nettest')
        self.assertIn('name', response_body['net-tests'][1])
        self.assertEqual(response_body['net-tests'][1]['name'], 'another_fake_nettest')

    @defer.inlineCallbacks
    def test_invalid_net_test(self):
        data = {
            'net-tests': [
                {
                    "test-helpers": [],
                    "input-hashes": [],
                    "name": 'invalid_nettest',
                    "version": '1.0',
                },
            ]
        }

        response = yield self.request('/bouncer/net-tests', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('error', response_body)
        self.assertEqual('collector-not-found', response_body['error'])

    @defer.inlineCallbacks
    def test_net_tests_with_input(self):
        data = {
            'net-tests': [
                {
                    "test-helpers": [],
                    "input-hashes": ['fake_id'],
                    "name": 'fake_nettest',
                    "version": '1.0',
                },
            ]
        }

        response = yield self.request('/bouncer/net-tests', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('net-tests', response_body)
        self.assertEqual(len(response_body['net-tests']), 1)
        self.assertIn('name', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['name'], 'fake_nettest')
        self.assertIn('input-hashes', response_body['net-tests'][0])
        self.assertEqual(len(response_body['net-tests'][0]['input-hashes']), 1)
        self.assertEqual(response_body['net-tests'][0]['input-hashes'][0], 'fake_id')

    @defer.inlineCallbacks
    def test_net_tests_with_input_invalid_id(self):
        data = {
            'net-tests': [
                {
                    "test-helpers": [],
                    "input-hashes": ['invalid_id'],
                    "name": 'fake_nettest',
                    "version": '1.0',
                },
            ]
        }

        response = yield self.request('/bouncer/net-tests', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('error', response_body)
        self.assertEqual('collector-not-found', response_body['error'])

    @defer.inlineCallbacks
    def test_net_tests_with_test_helper(self):
        data = {
            'net-tests': [
                {
                    "test-helpers": ['fake_test_helper'],
                    "input-hashes": [],
                    "name": 'fake_nettest',
                    "version": '1.0',
                },
            ]
        }

        response = yield self.request('/bouncer/net-tests', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('net-tests', response_body)
        self.assertEqual(len(response_body['net-tests']), 1)
        self.assertIn('name', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['name'], 'fake_nettest')
        self.assertIn('test-helpers', response_body['net-tests'][0])
        self.assertEqual(len(response_body['net-tests'][0]['test-helpers']), 1)
        self.assertEqual(response_body['net-tests'][0]['test-helpers']['fake_test_helper'], 'fake_hostname')

    @defer.inlineCallbacks
    def test_net_tests_with_invalid_test_helper(self):
        data = {
            'net-tests': [
                {
                    "test-helpers": ['invalid_test_helper'],
                    "input-hashes": [],
                    "name": 'fake_nettest',
                    "version": '1.0',
                },
            ]
        }

        response = yield self.request('/bouncer/net-tests', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('error', response_body)
        self.assertEqual('collector-not-found', response_body['error'])

    @defer.inlineCallbacks
    def test_invalid_request(self):
        data = {
            'something_weird': 'nsa'
        }

        response = yield self.request('/bouncer', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('error', response_body)
        self.assertEqual('test-helpers-or-net-test-key-missing', response_body['error'])


class TestDefaultCollector(BaseTestBouncer):
    app = web.Application(bouncerAPI, name='bouncerAPI')

    def setUp(self, *args, **kw):
        with open(bouncer_filename, 'w') as bouncer_file:
            bouncer_file.write(fake_default_collector)
        super(TestDefaultCollector, self).setUp()

    @defer.inlineCallbacks
    def test_default_collector(self):
        data = {
            'net-tests': [
                {
                    "test-helpers": [],
                    "input-hashes": [],
                    "name": 'imaginary_nettest',
                    "version": '1.0',
                }
            ]
        }

        response = yield self.request('/bouncer/net-tests', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('net-tests', response_body)
        self.assertEqual(len(response_body['net-tests']), 1)
        self.assertIn('name', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['name'], 'imaginary_nettest')
        self.assertIn('version', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['version'], '1.0')
        self.assertIn('input-hashes', response_body['net-tests'][0])
        self.assertEqual(len(response_body['net-tests'][0]['input-hashes']), 0)
        self.assertIn('test-helpers', response_body['net-tests'][0])
        self.assertEqual(len(response_body['net-tests'][0]['test-helpers']), 0)
        self.assertIn('collector', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['collector'], 'default_collector')


class TestMultipleCollectors(BaseTestBouncer):
    app = web.Application(bouncerAPI, name='bouncerAPI')

    def setUp(self, *args, **kw):
        with open(bouncer_filename, 'w') as bouncer_file:
            bouncer_file.write(fake_bouncer_file_multiple_collectors)
        super(TestMultipleCollectors, self).setUp()

    @defer.inlineCallbacks
    def test_multiple_collectors(self):
        data = {
            'net-tests': [
                {
                    "test-helpers": [],
                    "input-hashes": [],
                    "name": 'fake_nettest',
                    "version": '1.0',
                },
            ]
        }

        response = yield self.request('/bouncer/net-tests', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('net-tests', response_body)
        self.assertEqual(len(response_body['net-tests']), 1)
        self.assertIn('name', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['name'], 'fake_nettest')
        self.assertIn('version', response_body['net-tests'][0])
        self.assertEqual(response_body['net-tests'][0]['version'], '1.0')
        self.assertIn('input-hashes', response_body['net-tests'][0])
        self.assertEqual(len(response_body['net-tests'][0]['input-hashes']), 0)
        self.assertIn('test-helpers', response_body['net-tests'][0])
        self.assertEqual(len(response_body['net-tests'][0]['test-helpers']), 0)
        self.assertIn('collector', response_body['net-tests'][0])
        self.assertIn(response_body['net-tests'][0]['collector'], ['fake_addressA', 'fake_addressB'])


class TestHelperTests(BaseTestBouncer):
    app = web.Application(bouncerAPI, name='bouncerAPI')

    def setUp(self, *args, **kw):
        with open(bouncer_filename, 'w') as bouncer_file:
            bouncer_file.write(fake_for_test_helper_request)
        super(TestHelperTests, self).setUp()

    @defer.inlineCallbacks
    def test_invalid_helper(self):
        data = {
            'test-helpers': ['invalid_test_helper']
        }
        response = yield self.request('/bouncer/test-helpers', 'POST', data)
        response_body = json.loads(response.body)

        self.assertIn('error', response_body)
        self.assertEqual('test-helper-not-found', response_body['error'])

    @defer.inlineCallbacks
    def test_multiple_collectors(self):
        data = {
            'test-helpers': ['fake_test_helper']
        }

        response = yield self.request('/bouncer/test-helpers', 'POST', data)
        response_body = json.loads(response.body)

        self.assertEqual(len(response_body), 2)
        self.assertIn('fake_test_helper', response_body)
        self.assertIn('collector', response_body['fake_test_helper'])
        self.assertIn(response_body['fake_test_helper']['collector'], ['fake_addressA', 'fake_addressB'])
        self.assertIn('address', response_body['fake_test_helper'])
        self.assertEqual('fake_hostname', response_body['fake_test_helper']['address'])

        self.assertIn('default', response_body)
        self.assertIn('collector', response_body['default'])
        self.assertEqual('fake_addressB', response_body['default']['collector'])

    @defer.inlineCallbacks
    def test_backward_compatibility(self):
        data = {
            'test-helpers': ['fake_test_helper']
        }

        response = yield self.request('/bouncer', 'POST', data)
        response_body = json.loads(response.body)

        self.assertEqual(len(response_body), 2)
        self.assertIn('fake_test_helper', response_body)
        self.assertIn('collector', response_body['fake_test_helper'])
        self.assertIn(response_body['fake_test_helper']['collector'], ['fake_addressA', 'fake_addressB'])
        self.assertIn('address', response_body['fake_test_helper'])
        self.assertEqual('fake_hostname', response_body['fake_test_helper']['address'])

        self.assertIn('default', response_body)
        self.assertIn('collector', response_body['default'])
        self.assertEqual('fake_addressB', response_body['default']['collector'])

    @defer.inlineCallbacks
    def test_multiple_helpers(self):
        data = {
            'test-helpers': ['fake_test_helper', 'exotic_test_helper']
        }

        response = yield self.request('/bouncer/test-helpers', 'POST', data)
        response_body = json.loads(response.body)

        self.assertEqual(len(response_body), 3)
        self.assertIn('fake_test_helper', response_body)
        self.assertIn('exotic_test_helper', response_body)
        self.assertIn('default', response_body)
        self.assertIn(response_body['fake_test_helper']['collector'], ['fake_addressA', 'fake_addressB'])
        self.assertEqual(response_body['exotic_test_helper']['collector'], 'fake_addressA')
        self.assertEqual('fake_addressB', response_body['default']['collector'])
